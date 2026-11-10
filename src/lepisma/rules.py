"""The lint rules. Each takes a parsed block and returns findings."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from lepisma.models import Finding

if TYPE_CHECKING:
    from spacy.tokens import Doc, Span, Token

    from lepisma.config import Config
    from lepisma.markdown import Block

NOUNS = {"NOUN", "PROPN"}
# Verb lexicons by id(vocab), registered by engine.parse_blocks. Kept off the
# Doc so it never gets copied or serialized with one.
_VERB_LEXICONS: dict[int, frozenset[str]] = {}
_PLURAL_TAGS = {"NNS", "NNPS"}
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


# Suffix -> endings to try on the stem when looking for the source verb.
_DERIVATIONS = [
    ("ation", ("ate", "", "e")),  # create, inform, explore
    ("ition", ("", "e", "ish")),  # add, define, abolish
    ("tion", ("t", "te", "e")),  # adopt, complete, produce
    ("sion", ("d", "de", "t", "se")),  # extend, decide, convert, revise
    ("ment", ("",)),  # deploy
    ("ance", ("", "e", "ate")),  # perform, guide, tolerate
    ("ence", ("", "e")),  # depend, confide
]


def source_verb(noun: str, verbs: frozenset[str]) -> str | None:
    """The verb a noun derives from ("placement" -> "place"), checked against
    ``verbs``. None when the noun has no verb behind it ("fraction", "substance")."""
    noun = noun.lower()
    guess = verb_form(noun)
    if noun in VERB_FORMS or (guess and guess in verbs):
        return guess
    for suffix, endings in _DERIVATIONS:
        if noun.endswith(suffix):
            stem = noun[: -len(suffix)]
            for ending in endings:
                if len(stem) > 1 and stem + ending in verbs:
                    return stem + ending
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


def register_verbs(vocab: object, verbs: frozenset[str]) -> None:
    """Make ``verbs`` the verb lexicon for docs that share ``vocab``."""
    _VERB_LEXICONS[id(vocab)] = verbs


def verbs_of(doc: Doc) -> frozenset[str]:
    """The registered verb lexicon for ``doc``; empty when there is none."""
    return _VERB_LEXICONS.get(id(doc.vocab), frozenset())


_LABEL_MARKS = {":", "-", "\u2013", "\u2014"}


def _opens_clause(tok: Token, sent: Span) -> bool:
    """True for the first word of a sentence or list item, or the first word
    after a label ("Purpose: Test ...", "`fn()` - Validates ...")."""
    for prev in reversed(sent.doc[sent.start : tok.i]):
        if prev.text in _LABEL_MARKS and not _is_joiner(prev):
            return True
        if is_word(prev) and any(c.isalnum() for c in prev.text):
            return False  # "✅" is tagged ADJ, but it is a list marker
    return True


def _can_be_verb(tok: Token, verbs: frozenset[str]) -> bool:
    """True when the word, or the word without a third-person -s, is a verb."""
    lower = tok.lower_
    forms = {lower, tok.lemma_.lower()}
    if lower.endswith("s"):
        forms.add(lower[:-1])
        if lower.endswith("es"):
            forms.add(lower[:-2])
        if lower.endswith("ies"):
            forms.add(lower[:-3] + "y")
    return not forms.isdisjoint(verbs)


def _verb_like(
    tok: Token, group: list[Token], sent: Span, verbs: frozenset[str]
) -> bool:
    """A token in a noun run that is more likely a verb the tagger got wrong."""
    # "Test line number accuracy", "Checks notebook file existence": a list
    # item, sentence or labelled line that opens with a verb.
    if tok.i == group[0].i and _opens_clause(tok, sent) and _can_be_verb(tok, verbs):
        return True
    # A plural rarely modifies a later noun, so it ends a subject and a verb
    # follows: "toggle pins light/dark", "Claude Code loads ancestor files",
    # "Students reference error hints".
    last = tok.i == group[-1].i
    if not last and tok.tag_ in _PLURAL_TAGS:
        return True
    # "The student progress bar resets after a logout": the parser made the
    # verb the root of a noun phrase, in a sentence with no other verb.
    return (
        last
        and tok.dep_ == "ROOT"
        and tok.tag_ in _PLURAL_TAGS
        and _can_be_verb(tok, verbs)
        and group[0].i > sent.start
        and group[0].nbor(-1).pos_ == "DET"
        and not any(t.pos_ in {"VERB", "AUX"} for t in sent)
    )


def _trim_joiners(piece: list[Token]) -> list[Token]:
    start, end = 0, len(piece)
    while start < end and _is_joiner(piece[start]):
        start += 1
    while end > start and _is_joiner(piece[end - 1]):
        end -= 1
    return piece[start:end]


def _split_at_verbs(
    group: list[Token], sent: Span, verbs: frozenset[str]
) -> list[list[Token]]:
    """Drop verb-like tokens from a noun group and split it where they were."""
    pieces: list[list[Token]] = [[]]
    for tok in group:
        if _verb_like(tok, group, sent, verbs):
            pieces.append([])
        else:
            pieces[-1].append(tok)
    return [p for p in map(_trim_joiners, pieces) if p]


def stacks(block: Block, sent: Span, cfg: Config) -> Iterator[list[Token]]:
    """Noun groups in a sentence that R2 should report."""
    rule = cfg.noun_stack
    verbs = verbs_of(sent.doc)
    for run in noun_runs(block, sent):
        for group in _linked(run):
            if noun_count(group) < rule.min_nouns:
                continue
            for piece in _split_at_verbs(group, sent, verbs):
                if noun_count(piece) < rule.min_nouns:
                    continue
                propn = sum(1 for t in piece if t.pos_ == "PROPN")
                if rule.ignore_all_propn and propn == len(piece):
                    continue
                if propn > rule.max_proper_nouns:
                    continue
                yield piece


def noun_stack(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R2: four or more nouns in a row that modify each other."""
    rule = cfg.noun_stack
    if block.kind == "heading":
        return
    for sent in doc.sents:
        for group in stacks(block, sent, cfg):
            count = noun_count(group)
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


# Habit words that count only right before a verb: "successfully implemented"
# is status-report filler, "runs successfully" is a plain claim.
_BEFORE_VERB_ONLY = {"successfully"}


def _opens_item(tok: Token, block: Block) -> bool:
    """True for the first word of a list item or checklist line, or the first
    word after its label ("5. **Test contrast**: Ensure ...")."""
    sent = tok.sent
    if not _opens_clause(tok, sent):
        return False
    return block.kind == "list" or sent[0].idx in block.breaks


def _skip_habit(tok: Token, block: Block, cfg: Config) -> bool:
    lower = tok.lower_
    if lower in cfg.habit_words.ok_at_item_start and _opens_item(tok, block):
        return True  # "- Ensure the build passes": the natural checklist verb
    if lower in _BEFORE_VERB_ONLY:
        nxt = tok.nbor(1) if tok.i + 1 < len(tok.doc) else None
        return nxt is None or nxt.is_sent_start or nxt.pos_ not in {"VERB", "AUX"}
    return False


def habit_hits(block: Block, doc: Doc, cfg: Config) -> list[tuple[int, str]]:
    words = cfg.habit_words.words
    singles = {w for w in words if " " not in w}
    hits: list[tuple[int, str]] = []
    for tok in doc:
        if block.in_code(tok.idx, tok.idx + len(tok)):
            continue
        lower, lemma = tok.lower_, tok.lemma_.lower()
        if (lower in singles or lemma in singles) and _skip_habit(tok, block, cfg):
            continue
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


_COUNTED = {"a", "an", "one", "each", "every"}
_TRANSFER_VERBS = {"provide", "give", "offer"}


def _counted(noun: Token) -> bool:
    """True for a counted noun, like "one placement" or "a fraction": a thing,
    not an action."""
    return any(
        c.dep_ == "nummod" or (c.dep_ == "det" and c.lower_ in _COUNTED)
        for c in noun.children
    )


def _supplies_a_thing(verb: Token, noun: Token) -> bool:
    """True when the verb hands something over, so it is not a verb in disguise.

    That means a recipient ("provides guidance to Claude Code", "give every failure
    a representation") or a named deliverable ("provide image descriptions").
    """
    if any(c.dep_ == "dative" for c in verb.children):
        return True
    if any(
        c.dep_ == "prep" and c.lower_ == "to" for c in (*verb.children, *noun.children)
    ):
        return True
    return any(c.dep_ == "compound" for c in noun.children)


def _hidden_verb(tok: Token, cfg: Config) -> Token | None:
    """The nominal object of a weak verb (``performs validation``), if any."""
    lemma = tok.lemma_.lower()
    if lemma not in cfg.nominalization.weak_verbs:
        return None
    verbs = verbs_of(tok.doc)
    for child in tok.children:
        if child.dep_ not in {"dobj", "attr", "nsubjpass"}:
            continue
        if not is_nominal(child, cfg):
            continue
        # No verb behind the noun, so none is hidden: "are fractions of",
        # "provides flexibility". Without a lexicon, trust the suffix.
        if verbs and source_verb(child.lemma_, verbs) is None:
            continue
        has_of = any(c.dep_ == "prep" and c.lower_ == "of" for c in child.children)
        # "is the implementation of X" is weak; "is a solution" is just a noun,
        # "is one placement of" counts a thing, and "has every reference" is
        # plain possession.
        if lemma in {"be", "have"} and (not has_of or _counted(child)):
            continue
        if lemma in _TRANSFER_VERBS and _supplies_a_thing(tok, child):
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


_VERB_POS = {"VERB", "AUX"}
_AUX_DEPS = {"aux", "auxpass", "neg"}


def _verb_group_start(verb: Token) -> Token:
    """The first word of a verb group: "will" in "will be deleted"."""
    return min(
        (verb, *(c for c in verb.children if c.dep_ in _AUX_DEPS)), key=lambda t: t.i
    )


def _main_verb(sent: Span) -> Token | None:
    """The start of the first main-clause verb group, or None for a fragment.

    Main clauses are the root and any clause joined to it ("X is noise, so Y
    was checked"); the parser often makes the later one the root.
    """
    root = sent.root
    if root.pos_ not in _VERB_POS:
        return None
    clauses = [root]
    clauses.extend(
        t for t in root.children if t.dep_ in _JOINED and t.pos_ in _VERB_POS
    )
    # The parser sometimes hangs the first main clause under a later one; any
    # finite verb with its own subject and no "if"/"which" in front counts.
    clauses.extend(t for t in sent if _is_main_clause(t))
    return min((_verb_group_start(v) for v in clauses), key=lambda t: t.i)


_JOINED = {"conj", "parataxis"}
_FINITE_TAGS = {"VBZ", "VBP", "VBD", "MD"}
_SUBORDINATE = {"advcl", "relcl", "acl", "csubj", "csubjpass", "pcomp", "xcomp"}


def _is_main_clause(tok: Token) -> bool:
    if tok.pos_ not in _VERB_POS or tok.dep_ in _SUBORDINATE:
        return False
    group = [tok, *(c for c in tok.children if c.dep_ in _AUX_DEPS)]
    if not any(t.tag_ in _FINITE_TAGS for t in group):
        return False
    deps = {c.dep_ for c in tok.children}
    return bool(deps & {"nsubj", "nsubjpass", "expl"}) and "mark" not in deps


def _words_before(sent: Span, stop: Token, block: Block) -> int:
    """Words from the sentence start (or its last label mark) up to ``stop``."""
    count = 0
    for tok in sent.doc[sent.start : stop.i]:
        if (tok.text in _LABEL_MARKS or tok.text == ";") and not _is_joiner(tok):
            count = 0  # "**Status**: ...", "`fn()` - ..." or "...; then": restart
        elif is_word(tok):
            count += 1
    return count


def late_verb(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R5: too many words before the main verb."""
    rule = cfg.late_verb
    if block.kind == "heading":
        return
    for sent in doc.sents:
        verb = _main_verb(sent)
        if verb is None:
            continue
        before = _words_before(sent, verb, block)
        if before <= rule.max_words_before:
            continue
        strong = before > rule.strong_words_before
        first = next((t for t in sent if not t.is_space), sent[0])
        yield Finding(
            rule="R5",
            offset=first.idx,
            message=(
                f'{before} words before the main verb "{verb.text}"; '
                "put the subject and verb first."
            ),
            severity="strong" if strong else "warning",
        )


def _summary_opener(sent: Span, openers: list[str]) -> str | None:
    """The opener from ``openers`` that starts the sentence, if any."""
    text = sent.text.lstrip().lower()
    for opener in openers:
        low = opener.lower()
        if text.startswith(low) and not text[len(low) : len(low) + 1].isalnum():
            return low
    return None


def vague_this(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R6: a sentence whose subject is a bare "This" ("This allows ...")."""
    rule = cfg.vague_this
    if block.kind == "heading":
        return
    words = {w.lower() for w in rule.words}
    sents = list(doc.sents)
    for idx, sent in enumerate(sents):
        first = next((t for t in sent if is_word(t)), None)
        if first is None or first.lower_ not in words:
            continue
        # A determiner ("This flag ...") names its referent; only the bare
        # pronoun as subject is vague.
        if first.dep_ != "nsubj" or first.pos_ != "PRON":
            continue
        verb = first.head
        # "This is the last stage" is plain; "This allows ..." hides the actor.
        if verb.pos_ not in _VERB_POS or verb.lemma_ == "be":
            continue
        # R7 already reports a closing "This ensures ...".
        last = idx == len(sents) - 1 and len(sents) > 1
        summary = cfg.tidy_summary
        if last and summary.enabled and _summary_opener(sent, summary.openers):
            continue
        near = verb.i - first.i <= _MAX_PHRASE
        phrase = doc[first.i : verb.i + 1].text if near else first.text
        yield Finding(
            rule="R6",
            offset=first.idx,
            message=(
                f'"{phrase}": name what "{first.lower_}" is, '
                "or make the actor the subject."
            ),
        )


_MIN_SUMMARY_SENTS = 2  # a lone sentence has nothing to summarize


def tidy_summary(block: Block, doc: Doc, cfg: Config) -> Iterator[Finding]:
    """R7: a paragraph that ends by restating itself ("Overall, ...")."""
    if block.kind not in {"paragraph", "quote"}:
        return
    sents = [s for s in doc.sents if any(is_word(t) for t in s)]
    if len(sents) < _MIN_SUMMARY_SENTS:
        return
    last = sents[-1]
    opener = _summary_opener(last, cfg.tidy_summary.openers)
    if opener is None:
        return
    first = next(t for t in last if not t.is_space)
    said = last.text.lstrip()[: len(opener)]
    yield Finding(
        rule="R7",
        offset=first.idx,
        message=(
            f'Paragraph ends with a summary ("{said} ..."); cut it or add a new fact.'
        ),
    )


RuleFn = Callable[["Block", "Doc", "Config"], Iterator[Finding]]

RULE_FUNCS: dict[str, RuleFn] = {
    "R1": long_sentence,
    "R2": noun_stack,
    "R3": habit_words,
    "R4": nominalization,
    "R5": late_verb,
    "R6": vague_this,
    "R7": tidy_summary,
}
