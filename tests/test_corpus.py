"""The baseline test set: bad docs must score clearly worse than good ones."""

from collections import Counter
from pathlib import Path

from lepisma.config import Config
from lepisma.engine import lint_text
from lepisma.report import per_1000

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


OLD_STYLE = ("R1", "R2", "R3", "R4", "R5", "R6", "R7")


def _total(found: dict[str, float], *, old: bool) -> float:
    return sum(n for r, n in found.items() if r != "all" and (r in OLD_STYLE) == old)


def test_real_toolbox_docs_stay_quiet(nlp):
    """Real docs, mostly fine: catches old-style rules that flag normal prose."""
    found = densities("toolbox", nlp)
    assert _total(found, old=True) < 12
    assert max(found.get(rule, 0) for rule in ("R2", "R3", "R4")) < 1


def test_style_rules_find_the_toolbox_and_spare_the_good_docs(nlp):
    """R8 and later target how Claude writes now. The toolbox docs are real
    Claude output, so they are the positive set for these rules, and the good
    docs are the quiet one. A rule that is tuned down until the toolbox goes
    silent fails here."""
    toolbox = _total(densities("toolbox", nlp), old=False)
    good = _total(densities("good", nlp), old=False)
    assert toolbox > 3
    assert good < 1
