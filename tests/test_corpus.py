"""The baseline test set: bad docs must score clearly worse than good ones."""

from collections import Counter
from pathlib import Path

from prose_lint.config import Config
from prose_lint.engine import lint_text
from prose_lint.report import per_1000

CORPUS = Path(__file__).parent.parent / "corpus"


def densities(group: str, nlp) -> dict[str, float]:
    """Warnings per 1,000 words for a corpus folder: per rule, plus "all"."""
    words = 0
    counts: Counter[str] = Counter()
    for path in sorted((CORPUS / group).rglob("*.md")):
        result = lint_text(str(path), path.read_text(), Config(), nlp)
        words += result.words
        counts.update(w.rule for w in result.warnings)
    counts["all"] = sum(counts.values())
    return {rule: per_1000(n, words) for rule, n in counts.items()}


def test_bad_docs_score_far_worse_than_good_docs(nlp):
    bad, good = densities("bad", nlp)["all"], densities("good", nlp)["all"]
    assert bad > 30
    assert good < 10
    assert bad > 5 * good


def test_real_toolbox_docs_stay_quiet(nlp):
    """Real docs, mostly fine: catches rules that start flagging normal prose."""
    found = densities("toolbox", nlp)
    assert found["all"] < 12
    assert max(found.get(rule, 0) for rule in ("R2", "R3", "R4")) < 1
