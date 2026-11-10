"""Readability, dependency distance, POS shares and repetition for spaCy docs.

Ported from TextDescriptives 2.8 (Apache-2.0), which pins numpy<2 and so does
not install on Python 3.14. The formulas and token filters match it, so the
numbers stay comparable with earlier ``lepisma measure`` runs.
"""

from __future__ import annotations

from collections import defaultdict
from functools import cache
from statistics import fmean
from typing import TYPE_CHECKING

from pyphen import Pyphen

if TYPE_CHECKING:
    from collections.abc import Iterable

    from spacy.tokens import Doc, Span, Token

NAN = float("nan")


def _words(span: Doc | Span) -> list[Token]:
    """Tokens that count as words: no punctuation, no contractions like 's."""
    return [t for t in span if not t.is_punct and "'" not in t.text]


@cache
def _hyphenator(lang: str) -> Pyphen:
    return Pyphen(lang=lang)


def _syllables(token: Token, dic: Pyphen) -> int:
    return max(1, dic.inserted(token.lower_).count("-") + 1)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return fmean(values) if values else NAN


def readability(doc: Doc) -> dict[str, float]:
    """Flesch reading ease, Flesch-Kincaid grade, Gunning fog and LIX."""
    words = _words(doc)
    sent_len = _mean(len(_words(s)) for s in doc.sents)
    if not words:
        return dict.fromkeys(
            ("flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog", "lix"),
            NAN,
        )
    dic = _hyphenator(doc.lang_)
    syllables = [_syllables(t, dic) for t in words]
    syl_per_word = fmean(syllables)
    hard = sum(1 for s in syllables if s >= 3)  # noqa: PLR2004
    long_words = sum(1 for t in words if len(t) > 6)  # noqa: PLR2004
    flesch = sent_len > 0 and syl_per_word > 0
    return {
        "flesch_reading_ease": (
            206.835 - 1.015 * sent_len - 84.6 * syl_per_word if flesch else NAN
        ),
        "flesch_kincaid_grade": (
            0.39 * sent_len + 11.8 * syl_per_word - 15.59 if flesch else NAN
        ),
        "gunning_fog": 0.4 * (sent_len + hard / len(words) * 100),
        "lix": sent_len + long_words / len(words) * 100,
    }


def dependency_distance(sent: Span) -> float:
    """Mean distance from each token to its head; the root counts as zero."""
    return _mean(0 if t.dep_ == "ROOT" else abs(t.head.i - t.i) for t in sent)


def doc_dependency_distance(doc: Doc) -> float:
    """Mean of the per-sentence dependency distances."""
    return _mean(dependency_distance(s) for s in doc.sents)


def pos_proportions(doc: Doc, tags: Iterable[str]) -> dict[str, float]:
    """Share of all tokens, punctuation included, tagged with each POS tag."""
    counts: defaultdict[str, int] = defaultdict(int)
    for t in doc:
        counts[t.pos_] += 1
    n = len(doc)
    return {tag: counts[tag] / n if n else NAN for tag in tags}


def duplicate_ngram_chr_fraction(doc: Doc, n: int = 5) -> float:
    """Share of characters inside a token n-gram that occurs more than once.

    Overlapping duplicates are merged, so no character counts twice.
    """
    chr_len = len(doc.text)
    if chr_len == 0:
        return 0.0
    starts: defaultdict[str, list[int]] = defaultdict(list)
    for i in range(len(doc) - n + 1):
        starts[doc[i : i + n].text].append(i)
    dup = [False] * len(doc)
    for idx in starts.values():
        if len(idx) > 1:
            for i in idx:
                dup[i : i + n] = [True] * n
    chars, i = 0, 0
    while i < len(doc):
        if not dup[i]:
            i += 1
            continue
        j = i
        while j < len(doc) and dup[j]:
            j += 1
        chars += doc[i:j].end_char - doc[i:j].start_char
        i = j
    return chars / chr_len
