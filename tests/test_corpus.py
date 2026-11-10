"""The baseline test set: bad docs must score clearly worse than good ones."""

from pathlib import Path

from prose_lint.config import Config
from prose_lint.engine import lint_text
from prose_lint.report import per_1000

CORPUS = Path(__file__).parent.parent / "corpus"


def density(group: str, nlp) -> float:
    words = warnings = 0
    for path in sorted((CORPUS / group).glob("*.md")):
        result = lint_text(str(path), path.read_text(), Config(), nlp)
        words += result.words
        warnings += len(result.warnings)
    return per_1000(warnings, words)


def test_bad_docs_score_far_worse_than_good_docs(nlp):
    bad, good = density("bad", nlp), density("good", nlp)
    assert bad > 30
    assert good < 10
    assert bad > 5 * good
