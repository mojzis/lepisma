"""Counts of the patterns current Claude prose leans on, per sentence and per file.

``measure`` reports them as columns. They are measurements, not rules: a count
here says how often a pattern occurs, not that a reader pays for it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lepisma.rules import is_word

if TYPE_CHECKING:
    from collections.abc import Iterable

    from spacy.tokens import Doc, Span, Token

    from lepisma.markdown import Block

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

LABEL_WORDS = 4  # a dash or colon after this few words separates a label
MIN_COLON_TAIL = 2  # words after a colon for it to count as mid-sentence
PUNCHLINE_WORDS = 6
PUNCHLINE_AFTER = 12
MIN_ACRONYM = 2

_DASH = re.compile("\u2014|\\s--\\s|\\s\u2013\\s")  # em dash, --, spaced en dash
_PAREN = re.compile(r"\((?!s\))")
_COLON = re.compile(r":(?=\s+\S)")
_ARROW = re.compile("->|=>|\u2192|\u21d2")
_COMPOUND = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+){2,}\b")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_WORD = re.compile(r"[A-Za-z]")

_CONTRAST = re.compile(
    r"\bnot\b[^.;:()]{1,60}?\bbut\b"  # not X but Y
    r"|,\s+not\b"  # X, not Y
    r"|\brather than\b",
    re.IGNORECASE,
)
_NEGATED = re.compile(r"\b(?:is|are|was|were|does|do)(?:n't|n\u2019t| not)\b", re.I)
_CORRECTS = re.compile(
    r"^\W*(?:it|that|this|they)(?:'s|\u2019s|'re|\u2019re| is| are)\b", re.I
)

SINCERITY = frozenset({"genuinely", "exactly", "deliberately", "quietly", "silently"})
FIGURATIVE = frozenset(
    {"seam", "verdict", "shape", "rung", "floor", "land", "surface", "wire", "drift"}
)
_FIGURATIVE_PHRASE = re.compile(r"\bload-bearing\b", re.IGNORECASE)
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

_ACRONYM = re.compile(r"^[A-Z]{2,6}s?$")
# Acronyms a technical reader knows, and capitals used for stress.
KNOWN_ACRONYMS = frozenset(
    {
        "API", "URL", "URI", "HTTP", "HTTPS", "JSON", "CLI", "CI", "CD", "ID", "HTML",
        "CSS", "SQL", "PR", "OS", "UI", "YAML", "TOML", "CPU", "GPU", "RAM", "PDF",
        "UTF", "ASCII", "README", "MIT", "AI", "IDE", "SDK", "XML", "CSV", "SSH",
        "TCP", "IP", "DNS", "UUID", "REST", "FAQ", "EOF", "OK", "TODO", "FIXME",
        "NOTE", "NOT", "MUST", "NEVER", "ALWAYS", "DO", "ONLY", "ALL", "ANY", "NO",
        "AND", "OR", "WARNING", "IMPORTANT", "CODE", "TL", "DR", "US", "UK", "EU",
    }
)  # fmt: skip


def _words_in(text: str) -> int:
    return sum(1 for w in text.split() if _WORD.search(w))


def _is_item(block: Block, sent: Span) -> bool:
    return block.kind == "list" or sent.start_char in block.breaks


def interrupters(block: Block, sent: Span) -> dict[str, int]:
    """Marks that break into a sentence: dashes, parentheses, semicolons, colons.

    A dash or colon right after a short label ("`name` \u2014 description",
    "Note: ...") separates the label and does not count. Neither does a colon
    that only introduces code or ends the sentence.
    """
    text = sent.text
    item = _is_item(block, sent)
    dashes = [
        m
        for m in _DASH.finditer(text)
        if not (item and _words_in(text[: m.start()]) <= LABEL_WORDS)
    ]
    colons = [
        m
        for m in _COLON.finditer(text)
        if _words_in(text[: m.start()]) > LABEL_WORDS
        and _words_in(text[m.end() :].replace("CODE", "")) >= MIN_COLON_TAIL
    ]
    counts = {
        "em_dashes": len(dashes),
        "semicolons": text.count(";"),
        "parentheticals": len(_PAREN.findall(text)),
        "mid_colons": len(colons),
    }
    counts["interrupters"] = sum(counts.values())
    return counts


def contrast_frames(text: str, prev: str = "") -> int:
    """ "not X but Y", "X, not Y", "rather than", and "isn't X. It's Y" when
    ``prev`` is the sentence before."""
    count = len(_CONTRAST.findall(text))
    if prev and _NEGATED.search(prev) and _CORRECTS.match(text):
        count += 1
    return count


def _outside_code(block: Block, sent: Span) -> Iterable[Token]:
    return (t for t in sent if not block.in_code(t.idx, t.idx + len(t)))


def emphasis(block: Block, sent: Span) -> dict[str, int]:
    """Sincerity markers, importance flags and figurative house terms."""
    toks = list(_outside_code(block, sent))
    text = sent.text
    return {
        "sincerity": sum(1 for t in toks if t.lower_ in SINCERITY),
        "importance": len(_IMPORTANCE.findall(text)),
        "figurative": sum(1 for t in toks if t.lemma_.lower() in FIGURATIVE)
        + len(_FIGURATIVE_PHRASE.findall(text)),
    }


def _fragment(block: Block, sent: Span, words: int) -> tuple[int, int]:
    """(no verb, no subject) for a paragraph sentence; list items are exempt."""
    if block.kind != "paragraph" or _is_item(block, sent) or words < MIN_COLON_TAIL:
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
        for t in _outside_code(block, sent)
        if t.dep_ == "nsubj"
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


def _expansion(acronym: str) -> re.Pattern[str]:
    """Words whose initials spell ``acronym``: "Language Server Protocol"."""
    filler = r"(?:(?:of|the|and|for|to|in)\s+)?"
    parts = [rf"{re.escape(ch)}\w+" for ch in acronym]
    return re.compile(r"\b" + (r"[\s-]+" + filler).join(parts), re.IGNORECASE)


def unexpanded_acronyms(blocks: list[tuple[Block, Doc]]) -> list[str]:
    """Acronyms never spelled out up to the block after their first use."""
    first_use: dict[str, int] = {}
    for idx, (block, doc) in enumerate(blocks):
        for tok in doc:
            if not _ACRONYM.match(tok.text) or block.in_code(tok.idx, tok.idx + 1):
                continue
            name = tok.text.rstrip("s")
            if len(name) >= MIN_ACRONYM and name not in KNOWN_ACRONYMS:
                first_use.setdefault(name, idx)
    found = []
    for name, idx in first_use.items():
        near = " ".join(b.text for b, _ in blocks[: idx + 2])
        if not _expansion(name).search(near):
            found.append(name)
    return sorted(found)
