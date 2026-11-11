"""Counts of the patterns current Claude prose leans on, per sentence and per file.

``measure`` reports them as columns. They are measurements, not rules: a count
here says how often a pattern occurs, not that a reader pays for it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lepisma import rules
from lepisma.config import Config
from lepisma.rules import contrast_offsets, interrupter_counts, is_word

if TYPE_CHECKING:
    from spacy.tokens import Doc, Span

    from lepisma.markdown import Block

_DEFAULTS = Config()

COLUMNS = (
    "em_dashes",
    "semicolons",
    "parentheticals",
    "mid_colons",
    "interrupters",
    "contrast_frames",
    "sincerity",
    "importance",
    "figurative",
    "arrows",
    "hyphen_compounds",
    "no_verb",
    "no_subject",
    "punchline",
    "trailing_participle",
    "inanimate_actor",
    "block_bold_spans",
)

MIN_COLON_TAIL = 2  # words after a colon for it to count as mid-sentence
PUNCHLINE_WORDS = 6
PUNCHLINE_AFTER = 12

_ARROW = re.compile("->|=>|\u2192|\u21d2")
_COMPOUND = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+){2,}\b")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")


_IMPORTANCE = re.compile(
    r"\bthis matters\b|\bmatters (?:because|most|here)\b"
    r"|\bworth (?:noting|knowing|remembering|mentioning|calling out|stressing)\b"
    r"|\bimportantly\b|\bcrucially\b|\bthe point is\b"
    r"|\bkey (?:insight|point|takeaway)\b",
    re.IGNORECASE,
)

# Verbs that give a thing a mind or a will.
ANTHRO_VERBS = frozenset(
    {
        "want", "know", "think", "believe", "decide", "expect", "see", "notice",
        "understand", "care", "like", "love", "hate", "prefer", "hope", "trust",
        "refuse", "try", "feel", "remember", "forget", "learn", "realize", "worry",
        "complain", "agree", "promise", "insist", "unlock", "earn", "deserve",
        "admit", "lie",
    }
)  # fmt: skip
ANIMATE = frozenset(
    {
        "user", "developer", "author", "reader", "writer", "maintainer", "reviewer",
        "team", "human", "person", "people", "agent", "model", "caller", "client",
        "contributor", "engineer", "operator", "admin", "owner", "customer",
        "student", "teacher", "anyone", "someone", "everyone", "nobody",
    }
)  # fmt: skip
_SUBJECTS = {"nsubj", "nsubjpass", "expl", "csubj", "csubjpass"}
_FINITE = {"VBZ", "VBD"}
# "-ing" words that open a prepositional phrase, not a participle clause.
_ING_PREPS = frozenset(
    {"including", "according", "depending", "regarding", "following", "excluding"}
)


def interrupters(block: Block, sent: Span) -> dict[str, int]:
    """R8's counts of the marks that break into a sentence, under default settings."""
    counts = interrupter_counts(block, sent, _DEFAULTS)
    return {
        "em_dashes": counts["dashes"],
        "semicolons": counts["semicolons"],
        "parentheticals": counts["parentheses"],
        "mid_colons": counts["colons"],
        "interrupters": sum(counts.values()),
    }


def contrast_frames(text: str, prev: str = "") -> int:
    """R9's contrast frames in one sentence; ``prev`` is the sentence before."""
    return len(contrast_offsets(text, prev))


def emphasis(block: Block, sent: Span) -> dict[str, int]:
    """Sincerity markers, importance flags and R11's figurative terms."""
    rule = _DEFAULTS.emphasis
    lo, hi = sent.start_char, sent.end_char

    def count(words: list[str]) -> int:
        hits = rules.emphasis_hits(block, sent.doc, words)
        return sum(1 for offset, _ in hits if lo <= offset < hi)

    return {
        "sincerity": count(rule.sincerity),
        "importance": len(_IMPORTANCE.findall(sent.text)),
        "figurative": count(rule.figurative),
    }


def _fragment(block: Block, sent: Span, words: int) -> tuple[int, int]:
    """(no verb, no subject) for a paragraph sentence; list items are exempt."""
    if (
        block.kind != "paragraph"
        or sent.start_char in block.breaks
        or words < MIN_COLON_TAIL
    ):
        return 0, 0
    if not any(t.pos_ in {"VERB", "AUX"} for t in sent):
        return 1, 0
    root = sent.root
    finite = root.tag_ in _FINITE or any(
        c.dep_ in {"aux", "auxpass"} and c.tag_ in _FINITE for c in root.children
    )
    has_subject = any(c.dep_ in _SUBJECTS for c in root.children)
    return 0, int(root.pos_ in {"VERB", "AUX"} and finite and not has_subject)


def trailing_participles(sent: Span) -> int:
    """1 when the sentence ends with a ", verb-ing ..." clause."""
    last = max((t.i for t in sent if is_word(t)), default=-1)
    for tok in sent:
        if tok.tag_ != "VBG" or tok.i == sent.start or tok.nbor(-1).text != ",":
            continue
        if tok.lower_ in _ING_PREPS or tok.head.tag_ == "VBG":
            continue  # a preposition, or one item in a list of "-ing" words
        if tok.dep_ in {"advcl", "acl", "conj", "xcomp"} and tok.right_edge.i >= last:
            return 1
    return 0


def inanimate_actors(block: Block, sent: Span) -> int:
    """Things that want, know or decide: "the parser wants"."""
    return sum(
        1
        for t in sent
        if not block.in_code(t.idx, t.idx + len(t))
        and t.dep_ == "nsubj"
        and t.pos_ == "NOUN"
        and t.lemma_.lower() not in ANIMATE
        and t.head.pos_ == "VERB"
        and t.head.lemma_.lower() in ANTHRO_VERBS
    )


def sentence_signals(
    block: Block, sent: Span, words: int, prev: Span | None, prev_words: int
) -> dict[str, int]:
    """Every per-sentence count. ``prev`` is the sentence before in the block."""
    text = sent.text
    no_verb, no_subject = _fragment(block, sent, words)
    first = prev is None
    return {
        **interrupters(block, sent),
        "contrast_frames": contrast_frames(text, prev.text if prev else ""),
        **emphasis(block, sent),
        "arrows": len(_ARROW.findall(text)),
        "hyphen_compounds": len(_COMPOUND.findall(text)),
        "no_verb": no_verb,
        "no_subject": no_subject,
        "punchline": int(
            not first and words <= PUNCHLINE_WORDS and prev_words >= PUNCHLINE_AFTER
        ),
        "trailing_participle": trailing_participles(sent),
        "inanimate_actor": inanimate_actors(block, sent),
        # A block's bold spans sit on its first sentence, so sums stay right.
        "block_bold_spans": len(_BOLD.findall(" ".join(block.raw))) if first else 0,
    }


def unexpanded_acronyms(blocks: list[tuple[Block, Doc]]) -> list[str]:
    """R10's acronyms that are never spelled out near their first use."""
    return sorted(name for name, _, _ in rules.unexpanded_acronyms(blocks, _DEFAULTS))
