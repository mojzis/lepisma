"""Run the rules over Markdown text. Imports spaCy, so only the server and the
in-process ``check`` command load this module."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import replace
from functools import cache, lru_cache
from typing import TYPE_CHECKING

from lepisma import markdown
from lepisma.config import ALL_DISABLED, RULES, Config, ConfigError, CustomRule
from lepisma.models import FileResult, Finding, Warning
from lepisma.rules import DOC_RULE_FUNCS, RULE_FUNCS, doc_words, register_verbs

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.matcher import Matcher
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


@lru_cache(maxsize=256)
def _compiled(nlp: Language, spec: str) -> Matcher:
    from spacy.matcher import Matcher  # noqa: PLC0415 - heavy import

    patterns, words = json.loads(spec)
    for entry in words:
        parts = entry.split()
        if len(parts) == 1:
            patterns.append([{"LEMMA": {"REGEX": f"(?i)^{re.escape(entry)}$"}}])
        patterns.append([{"LOWER": part} for part in parts])
    matcher = Matcher(nlp.vocab, validate=True)
    matcher.add("custom", patterns, greedy="LONGEST")
    return matcher


def custom_matcher(nlp: Language, rule: CustomRule) -> Matcher:
    """The spaCy Matcher for ``rule``, built once per rule text.

    Raises ConfigError for a pattern spaCy rejects.
    """
    try:
        return _compiled(nlp, json.dumps([rule.patterns, rule.words], sort_keys=True))
    except ValueError as exc:  # MatchPatternError and bad operators
        first = str(exc).strip().splitlines()[0]
        msg = f"[custom.{rule.name}] bad pattern: {first}"
        raise ConfigError(msg) from exc


def check_custom(nlp: Language, cfg: Config) -> None:
    """Compile every custom rule, so a bad pattern fails before any file is read."""
    for rule in cfg.custom:
        custom_matcher(nlp, rule)


def custom_findings(
    nlp: Language, block: markdown.Block, doc: Doc, rule: CustomRule
) -> Iterator[Finding]:
    """Hits of one custom rule in one block.

    ``{match}`` in the message is the matched text, ``{lemma}`` its lemmas and
    ``{head}`` the word the match hangs from ("take" for the "out" of "take it
    out"). An ``allow`` entry names a match to skip by its text, its lemmas, or
    the head's lemma and the text ("set up").
    """
    allow = set(rule.allow)
    for _, start, end in custom_matcher(nlp, rule)(doc):
        span = doc[start:end]
        if block.in_code(span.start_char, span.end_char):
            continue
        head = span.root.head
        with_head = f"{head.lemma_} {span.text}".lower()
        if allow & {span.text.lower(), span.lemma_.lower(), with_head}:
            continue
        message = (
            rule.message.replace("{match}", span.text)
            .replace("{lemma}", span.lemma_)
            .replace("{head}", head.text)
        )
        yield Finding(
            rule=rule.name,
            offset=span.start_char,
            message=message,
            severity=rule.severity,  # ty: ignore[invalid-argument-type]
        )


def lint_text(
    path: str, text: str, cfg: Config, nlp: Language | None = None
) -> FileResult:
    """Lint one Markdown document."""
    nlp = nlp or load_nlp()
    if cfg.undefined_term.glossary and cfg.spells_out(path):
        # This file is read without the glossary at hand: R10 runs without it.
        cfg = replace(cfg, undefined_term=replace(cfg.undefined_term, glossary={}))
    blocks = [b for b in markdown.parse(text) if not b.is_identifier_list_item()]
    enabled = [rid for rid, (_, attr) in RULES.items() if getattr(cfg, attr).enabled]
    parsed = list(zip(blocks, parse_blocks(nlp, blocks), strict=True))
    custom = [rule for rule in cfg.custom if rule.enabled]
    check_custom(nlp, cfg)
    found: list[tuple[markdown.Block, Finding]] = []
    for block, doc in parsed:
        for rule in custom if block.kind != "heading" else ():
            found.extend((block, f) for f in custom_findings(nlp, block, doc, rule))
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
        builtin = finding.rule in RULES
        if not builtin and ALL_DISABLED in block.disabled:
            continue
        line, col = block.position(finding.offset)
        warnings.append(
            Warning(
                path=path,
                line=line,
                col=col,
                rule=finding.rule,
                name=RULES[finding.rule][0] if builtin else finding.rule,
                severity=finding.severity,
                message=finding.message,
            )
        )
    warnings.sort(key=lambda w: (w.line, w.col, w.rule))
    return FileResult(path=path, words=doc_words(parsed), warnings=tuple(warnings))
