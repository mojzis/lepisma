"""Run the rules over Markdown text. Imports spaCy, so only the server and the
in-process ``check`` command load this module."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from prose_lint import markdown
from prose_lint.config import RULES, Config
from prose_lint.models import FileResult, Warning
from prose_lint.rules import RULE_FUNCS

if TYPE_CHECKING:
    from spacy.language import Language

MODEL = "en_core_web_sm"


@cache
def load_nlp() -> Language:
    """Load the spaCy model once per process."""
    import spacy  # noqa: PLC0415 - heavy import, kept off the hook's path

    return spacy.load(MODEL, disable=["ner"])


def lint_text(
    path: str, text: str, cfg: Config, nlp: Language | None = None
) -> FileResult:
    """Lint one Markdown document."""
    nlp = nlp or load_nlp()
    blocks = [b for b in markdown.parse(text) if not b.is_identifier_list_item()]
    enabled = [rid for rid, (_, attr) in RULES.items() if getattr(cfg, attr).enabled]
    warnings: list[Warning] = []
    words = 0
    for block, doc in zip(blocks, nlp.pipe(b.text for b in blocks), strict=True):
        words += sum(1 for t in doc if not (t.is_punct or t.is_space))
        for rid in enabled:
            if rid in block.disabled:
                continue
            for finding in RULE_FUNCS[rid](block, doc, cfg):
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
    return FileResult(path=path, words=words, warnings=tuple(warnings))
