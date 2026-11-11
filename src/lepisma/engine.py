"""Run the rules over Markdown text. Imports spaCy, so only the server and the
in-process ``check`` command load this module."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from functools import cache
from typing import TYPE_CHECKING

from lepisma import markdown
from lepisma.config import RULES, Config
from lepisma.models import FileResult, Finding, Warning
from lepisma.rules import DOC_RULE_FUNCS, RULE_FUNCS, doc_words, register_verbs

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.tokens import Doc


@cache
def load_nlp() -> Language:
    """Load the spaCy model once per process, downloading it on first use."""
    import spacy  # noqa: PLC0415 - heavy import, kept off the hook's path

    from lepisma.spacy_model import locate  # noqa: PLC0415

    return spacy.load(locate(), disable=["ner"])


@cache
def verb_lexicon(nlp: Language) -> frozenset[str]:
    """Base forms of English verbs, from the lemmatizer's WordNet index.

    Empty when the pipeline has no rule lemmatizer. Rules use it to tell a verb
    that the tagger called a noun ("Test line number accuracy") from a real noun.
    """
    if "lemmatizer" not in nlp.pipe_names:
        return frozenset()
    lookups = nlp.get_pipe("lemmatizer").lookups  # ty: ignore[unresolved-attribute]
    if not lookups.has_table("lemma_index"):
        return frozenset()
    return frozenset(lookups.get_table("lemma_index").get("verb", ()))


def parse_blocks(
    nlp: Language, blocks: Iterable[markdown.Block], batch_size: int | None = None
) -> Iterator[Doc]:
    """Run spaCy over blocks, starting a sentence at each ``Block.breaks`` offset.

    The parser keeps sentence starts that are set before it runs, so a line-per-item
    list splits into items even when the lines carry no end punctuation.
    """

    register_verbs(nlp.vocab, verb_lexicon(nlp))

    def docs() -> Iterator[Doc]:
        for block in blocks:
            doc = nlp.make_doc(block.text)
            starts = set(block.breaks)
            for tok in doc:
                if tok.idx in starts:
                    tok.is_sent_start = True
            yield doc

    return nlp.pipe(docs(), batch_size=batch_size)


def lint_text(
    path: str, text: str, cfg: Config, nlp: Language | None = None
) -> FileResult:
    """Lint one Markdown document."""
    nlp = nlp or load_nlp()
    blocks = [b for b in markdown.parse(text) if not b.is_identifier_list_item()]
    enabled = [rid for rid, (_, attr) in RULES.items() if getattr(cfg, attr).enabled]
    parsed = list(zip(blocks, parse_blocks(nlp, blocks), strict=True))
    found: list[tuple[markdown.Block, Finding]] = []
    for block, doc in parsed:
        found.extend(
            (block, finding)
            for rid in enabled
            if rid in RULE_FUNCS
            for finding in RULE_FUNCS[rid](block, doc, cfg)
        )
    for rid in enabled:
        if rid in DOC_RULE_FUNCS:
            found.extend(
                (parsed[idx][0], finding)
                for idx, finding in DOC_RULE_FUNCS[rid](parsed, cfg)
            )
    warnings: list[Warning] = []
    for block, finding in found:
        if finding.rule in block.disabled:
            continue
        line, col = block.position(finding.offset)
        warnings.append(
            Warning(
                path=path,
                line=line,
                col=col,
                rule=finding.rule,
                name=RULES[finding.rule][0],
                severity=finding.severity,
                message=finding.message,
            )
        )
    warnings.sort(key=lambda w: (w.line, w.col, w.rule))
    return FileResult(path=path, words=doc_words(parsed), warnings=tuple(warnings))
