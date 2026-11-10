import math

import pytest
import spacy
from spacy.tokens import Doc

from lepisma.textstats import (
    dependency_distance,
    doc_dependency_distance,
    duplicate_ngram_chr_fraction,
    pos_proportions,
    readability,
)


@pytest.fixture(scope="module")
def blank():
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def test_readability_one_syllable_words(blank):
    read = readability(blank("The cat sat."))
    # 3 words, 1 sentence, 1 syllable each, no hard or long words
    assert read["flesch_reading_ease"] == pytest.approx(206.835 - 1.015 * 3 - 84.6)
    assert read["flesch_kincaid_grade"] == pytest.approx(0.39 * 3 + 11.8 - 15.59)
    assert read["gunning_fog"] == pytest.approx(0.4 * 3)
    assert read["lix"] == pytest.approx(3)


def test_readability_hard_and_long_words(blank):
    read = readability(blank("Documentation helps. Contractions don't count."))
    # words: Documentation helps Contractions do count ("n't" is dropped)
    assert read["gunning_fog"] == pytest.approx(0.4 * (2.5 + 2 / 5 * 100))
    assert read["lix"] == pytest.approx(2.5 + 2 / 5 * 100)


def test_readability_without_words_is_nan(blank):
    assert all(math.isnan(v) for v in readability(blank("...")).values())


def _parsed(blank, words, heads, deps, pos=None):
    return Doc(blank.vocab, words=words, heads=heads, deps=deps, pos=pos)


def test_dependency_distance_counts_root_as_zero(blank):
    doc = _parsed(blank, ["I", "like", "green", "tea"], [1, 1, 3, 1],
                  ["nsubj", "ROOT", "amod", "dobj"])  # fmt: skip
    assert dependency_distance(doc[:]) == pytest.approx((1 + 0 + 1 + 2) / 4)
    assert doc_dependency_distance(doc) == pytest.approx(1.0)


def test_doc_dependency_distance_averages_sentences(blank):
    doc = _parsed(blank, ["Go", ".", "I", "like", "tea"], [0, 0, 3, 3, 3],
                  ["ROOT", "punct", "nsubj", "ROOT", "dobj"])  # fmt: skip
    # sentence means: (0 + 1) / 2 and (1 + 0 + 1) / 3
    assert doc_dependency_distance(doc) == pytest.approx((0.5 + 2 / 3) / 2)


def test_pos_proportions_include_punctuation(blank):
    doc = _parsed(blank, ["Cats", "sleep", "."], [1, 1, 1],
                  ["nsubj", "ROOT", "punct"], ["NOUN", "VERB", "PUNCT"])  # fmt: skip
    assert pos_proportions(doc, ("NOUN", "VERB", "ADJ")) == pytest.approx(
        {"NOUN": 1 / 3, "VERB": 1 / 3, "ADJ": 0.0}
    )


def test_pos_proportions_of_empty_doc_are_nan(blank):
    assert math.isnan(pos_proportions(blank(""), ("NOUN",))["NOUN"])


def test_duplicate_ngrams_merge_overlaps(blank):
    doc = blank("a b c d e x a b c d e")
    assert duplicate_ngram_chr_fraction(doc, 5) == pytest.approx(18 / len(doc.text))
    # a 6-word repeat covers the overlapping 5-grams once, not twice
    doc = blank("a b c d e f x a b c d e f")
    assert duplicate_ngram_chr_fraction(doc, 5) == pytest.approx(22 / len(doc.text))


def test_duplicate_ngrams_none_or_empty(blank):
    assert duplicate_ngram_chr_fraction(blank("one two three four five six")) == 0.0
    assert duplicate_ngram_chr_fraction(blank("")) == 0.0
