"""The four starter rules. Each takes a parsed block and returns findings."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from prose_lint.models import Finding

if TYPE_CHECKING:
    from spacy.tokens import Doc, Span, Token

    from prose_lint.config import Config
    from prose_lint.markdown import Block

NOUNS = {"NOUN", "PROPN"}
_MAX_PHRASE = 5  # quote "verb ... noun" in R4 messages only when this close

# Nominalization -> verb, for common cases the suffix rules get wrong.
VERB_FORMS = {
    "adoption": "adopt",
    "application": "apply",
    "assumption": "assume",
    "authentication": "authenticate",
    "completion": "complete",
    "consumption": "consume",
    "conversion": "convert",
    "correction": "correct",
    "decision": "decide",
    "deletion": "delete",
    "description": "describe",
    "detection": "detect",
    "discussion": "discuss",
    "exclusion": "exclude",
    "expansion": "expand",
    "extraction": "extract",
    "inclusion": "include",
    "indication": "indicate",
    "inspection": "inspect",
    "introduction": "introduce",
    "observation": "observe",
    "prevention": "prevent",
    "protection": "protect",
    "recommendation": "recommend",
    "reduction": "reduce",
    "revision": "revise",
    "selection": "select",
    "submission": "submit",
    "assistance": "assist",
    "avoidance": "avoid",
    "compliance": "comply",
    "configuration": "configure",
    "consideration": "consider",
    "dependence": "depend",
    "documentation": "document",
    "execution": "execute",
    "existence": "exist",
    "explanation": "explain",
    "installation": "install",
    "implementation": "implement",
    "maintenance": "maintain",
    "occurrence": "occur",
    "preference": "prefer",
    "reliance": "rely",
    "resolution": "resolve",
    "utilization": "use",
    "verification": "verify",
    "modification": "modify",
    "notification": "notify",
    "specification": "specify",
    "identification": "identify",
}
_SUFFIX_VERBS = [("ization", "ize"), ("isation", "ise"), ("ation", "ate")]
_ATE_OK = re.compile(
    r"(valid|cre|migr|integr|gener|autom|evalu|calcul|separ|oper|activ|termin"
    r"|isol|initi|loc|repl|negoti|navig|investig|aggreg|deleg|alloc|rot|upd)ation$"
)


def verb_form(noun: str) -> str | None:
    """Best guess at the verb hidden in a nominalization, or None."""
    noun = noun.lower()
    if noun in VERB_FORMS:
        return VERB_FORMS[noun]
    for suffix, repl in _SUFFIX_VERBS[:2]:
        if noun.endswith(suffix):
            return noun[: -len(suffix)] + repl
    if _ATE_OK.search(noun):
        return noun[: -len("ation")] + "ate"
    if noun.endswith("ment") and len(noun) > len("ment") + 3:
        return noun[: -len("ment")]
    return None


def is_word(tok: Token) -> bool:
    return not (tok.is_punct or tok.is_space or tok.pos_ in {"SYM", "X", "SPACE"})


def long_sentence(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R1: sentences with too many words."""
    rule = cfg.long_sentence
    if block.kind == "heading":
        return
    for sent in doc.sents:
        words = sum(1 for tok in sent if is_word(tok))
        if words <= rule.max_words:
            continue
        strong = words > rule.strong_words
        advice = "split it" if strong else "consider splitting"
        first = next((t for t in sent if not t.is_space), sent[0])
        yield Finding(
            rule="R1",
            offset=first.idx,
            message=f"Sentence has {words} words; {advice}.",
            severity="strong" if strong else "warning",
        )


def _is_joiner(tok: Token) -> bool:
    """A hyphen or slash glued to both neighbours, as in "ty-find" or "read/write"."""
    doc = tok.doc
    return (
        tok.text in {"-", "/"}
        and 0 < tok.i < len(doc) - 1
        and not doc[tok.i - 1].whitespace_
        and not tok.whitespace_
    )


def _is_noun(block: Block, tok: Token) -> bool:
    return (
        tok.pos_ in NOUNS
        and any(c.isalpha() for c in tok.text)
        and not block.in_code(tok.idx, tok.idx + len(tok))
    )


def noun_runs(block: Block, sent: Span) -> Iterator[list[Token]]:
    run: list[Token] = []
    for tok in sent:
        if _is_noun(block, tok):
            run.append(tok)
            continue
        if run and _is_joiner(tok) and _is_noun(block, tok.nbor(1)):
            run.append(tok)
            continue
        if run:
            yield run
        run = []
    if run:
        yield run


def noun_count(group: list[Token]) -> int:
    """Nouns in a group, counting "ty-find" as one."""
    return sum(
        1
        for t in group
        if not _is_joiner(t) and not (t.i > 0 and _is_joiner(t.doc[t.i - 1]))
    )


def _linked(run: list[Token]) -> list[list[Token]]:
    """Split a run where a noun does not modify a later noun in the same run."""
    groups: list[list[Token]] = [[]]
    for idx, tok in enumerate(run):
        groups[-1].append(tok)
        last = idx == len(run) - 1
        inside = run[0].i <= tok.head.i <= run[-1].i
        if (
            not last
            and not inside
            and not _is_joiner(tok)
            and not _is_joiner(run[idx + 1])
        ):
            groups.append([])
    return groups


def noun_stack(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R2: three or more nouns in a row that modify each other."""
    rule = cfg.noun_stack
    if block.kind == "heading":
        return
    for sent in doc.sents:
        for run in noun_runs(block, sent):
            for group in _linked(run):
                count = noun_count(group)
                if count < rule.min_nouns:
                    continue
                if rule.ignore_all_propn and all(t.pos_ == "PROPN" for t in group):
                    continue
                strong = count >= rule.strong_nouns
                phrase = "".join(t.text_with_ws for t in group).strip()
                yield Finding(
                    rule="R2",
                    offset=group[0].idx,
                    message=(
                        f'Stack of {count} nouns ("{phrase}"); '
                        "rephrase with a verb or preposition."
                    ),
                    severity="strong" if strong else "warning",
                )


def habit_hits(block: Block, doc: Doc, cfg: Config) -> list[tuple[int, str]]:
    words = cfg.habit_words.words
    singles = {w for w in words if " " not in w}
    hits: list[tuple[int, str]] = []
    for tok in doc:
        if block.in_code(tok.idx, tok.idx + len(tok)):
            continue
        lower, lemma = tok.lower_, tok.lemma_.lower()
        if lower in singles:
            hits.append((tok.idx, lower))
        elif lemma in singles:
            hits.append((tok.idx, lemma))
    text = block.text.lower()
    for phrase in (w for w in words if " " in w):
        pattern = r"\b" + r"\s+".join(map(re.escape, phrase.split())) + r"\b"
        hits.extend((m.start(), phrase) for m in re.finditer(pattern, text))
    return sorted(hits)


def habit_words(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R3: words and phrases Claude overuses."""
    rule = cfg.habit_words
    hits = habit_hits(block, doc, cfg)
    strong = len(hits) > rule.max_per_paragraph
    for offset, word in hits:
        hint = rule.words.get(word, "")
        extra = f" ({len(hits)} in this paragraph)" if strong else ""
        advice = f"try: {hint}" if hint else "say it plainly"
        yield Finding(
            rule="R3",
            offset=offset,
            message=f'Habit word "{word}"{extra}; {advice}.',
            severity="strong" if strong else "warning",
        )


def is_nominal(tok: Token, cfg: Config) -> bool:
    rule = cfg.nominalization
    if tok.pos_ != "NOUN":
        return False
    word = tok.lemma_.lower()
    if len(word) < rule.min_length or word in rule.stoplist:
        return False
    return word.endswith(tuple(rule.suffixes))


def _hidden_verb(tok: Token, cfg: Config) -> Token | None:
    """The nominal object of a weak verb (``performs validation``), if any."""
    if tok.lemma_.lower() not in cfg.nominalization.weak_verbs:
        return None
    for child in tok.children:
        if child.dep_ not in {"dobj", "attr", "nsubjpass"}:
            continue
        if not is_nominal(child, cfg):
            continue
        has_of = any(c.dep_ == "prep" and c.lower_ == "of" for c in child.children)
        # "is the implementation of X" is weak; "is a solution" is just a noun,
        # and "has every reference" is plain possession.
        if tok.lemma_.lower() in {"be", "have"} and not has_of:
            continue
        return child
    return None


def nominalization(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R4: abstract nouns doing a verb's job."""
    rule = cfg.nominalization
    if block.kind == "heading":
        return
    for sent in doc.sents:
        nominals = [t for t in sent if is_nominal(t, cfg)]
        dense = len(nominals) >= rule.max_per_sentence
        pairs = [(t, n) for t in sent if (n := _hidden_verb(t, cfg)) is not None]
        for verb, noun in pairs:
            guess = verb_form(noun.lemma_)
            advice = f'try "{guess}"' if guess else "use the verb directly"
            lo, hi = sorted((verb.i, noun.i))
            phrase = doc[lo : hi + 1].text if hi - lo <= _MAX_PHRASE else verb.text
            yield Finding(
                rule="R4",
                offset=verb.idx,
                message=f'"{phrase}" hides the verb; {advice}.',
                severity="strong" if dense else "warning",
            )
        if dense and not pairs:
            listed = ", ".join(t.text for t in nominals[:5])
            yield Finding(
                rule="R4",
                offset=nominals[0].idx,
                message=(
                    f"{len(nominals)} abstract nouns in one sentence ({listed}); "
                    "turn some into verbs."
                ),
            )


RuleFn = Callable[["Block", "Doc", "Config"], Iterator[Finding]]

RULE_FUNCS: dict[str, RuleFn] = {
    "R1": long_sentence,
    "R2": noun_stack,
    "R3": habit_words,
    "R4": nominalization,
}
