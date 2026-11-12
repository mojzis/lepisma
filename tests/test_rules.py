import re
from pathlib import Path

import pytest

from lepisma.config import RULES, Config, from_dict
from lepisma.engine import lint_text
from lepisma.rules import verb_form


def rules(warnings):
    return [w.rule for w in warnings]


def test_long_sentence_warns_then_strong(lint):
    clause = "we read the file and then we print it"  # 9 words
    words26 = f"{clause}, {clause}, and so we stop the run here now."
    words40 = (
        f"{clause}, {clause}, {clause}, {clause}, and so we stop the run here now."
    )
    (w26,) = [w for w in lint(words26) if w.rule == "R1"]
    (w40,) = [w for w in lint(words40) if w.rule == "R1"]
    assert (w26.rule, w26.severity, w26.message) == (
        "R1",
        "warning",
        "Sentence has 26 words; consider splitting.",
    )
    assert w40.severity == "strong"


def test_short_sentence_is_clean(lint):
    assert lint("The tool reads the file and prints a warning.") == []


def test_noun_stack(lint):
    warnings = lint("Check the pipeline configuration validation error handling code.")
    (w,) = [w for w in warnings if w.rule == "R2"]
    assert w.message.startswith("Stack of ")
    assert '"pipeline configuration validation error' in w.message


def test_three_noun_technical_terms_are_fine(lint):
    assert "R2" not in rules(lint("The server listens on a Unix domain socket."))


def test_hyphenated_name_counts_as_one_noun(lint):
    # Without merging, "event - store connection pool" would count as 4 nouns.
    assert "R2" not in rules(lint("Check the event-store connection pool."))
    (w,) = lint("Check the event-store connection pool size.")
    assert w.message.startswith('Stack of 4 nouns ("event-store connection pool size")')


def test_have_needs_of_to_count_as_weak(lint):
    assert "R4" not in rules(lint("The index has every reference."))


def test_code_breaks_a_noun_stack(lint):
    assert "R2" not in rules(lint("Set the `retry_policy` option value."))


def test_habit_words_match_inflections_and_phrases(lint):
    warnings = lint("We leveraged it.\n\nIt is fine in order to test.")
    hits = [w.message for w in warnings if w.rule == "R3"]
    assert hits == [
        'Habit word "leverage"; try: use.',
        'Habit word "in order to"; try: to.',
    ]


def test_habit_words_turn_strong_above_two_per_paragraph(lint):
    warnings = lint("A robust, seamless and comprehensive tool.")
    assert [w.severity for w in warnings if w.rule == "R3"] == ["strong"] * 3


def test_habit_words_inside_code_are_ignored(lint):
    assert lint("Call `utilize()` here.\n\n```\nleverage\n```\n") == []


def test_nominalization_with_weak_verb(lint):
    (w,) = [
        w
        for w in lint("The service performs validation of the input.")
        if w.rule == "R4"
    ]
    assert w.message == '"performs validation" hides the verb; try "validate".'


def test_plain_verb_is_clean(lint):
    assert "R4" not in rules(lint("The service validates the input."))


def test_concrete_nouns_are_not_nominalizations(lint):
    assert "R4" not in rules(lint("The function has a comment."))


@pytest.mark.parametrize(
    ("noun", "verb"),
    [
        ("validation", "validate"),
        ("optimization", "optimize"),
        ("deployment", "deploy"),
        ("decision", "decide"),
        ("information", None),
    ],
)
def test_verb_form(noun, verb):
    assert verb_form(noun) == verb


def test_inline_disable_suppresses_rule(lint):
    text = "<!-- lepisma: disable R3 -->\nWe leverage it.\n"
    assert lint(text) == []


def test_disabled_rule_in_config(lint):
    cfg = from_dict({"rules": {"habit-word": {"enabled": False}}})
    assert lint("We leverage it.", cfg) == []


def test_headings_only_get_habit_word_rule(lint):
    warnings = lint("# Robust pipeline configuration validation error handling\n")
    assert rules(warnings) == ["R3"]


def test_positions_point_at_source(lint):
    (w,) = lint("Intro.\n\nSome text, `x`, then we utilize it.\n")
    assert (w.line, w.col) == (3, 25)


def test_default_config_is_valid():
    assert Config().long_sentence.max_words == 25


def test_unpunctuated_checkmark_lines_are_separate_sentences(lint):
    source = (
        "✅ Loader picks up new theme folders without restart\n"
        "✅ Help page renders on narrow mobile screens\n"
        "✅ Progress bar resets after the student logs out\n"
    )
    assert "R1" not in rules(lint(source))


def test_bold_label_lines_are_separate_sentences(lint):
    source = (
        "**Target**: Secure Python code execution in the browser via Pyodide\n"
        "**Context**: The drawing app runs user code in the main thread today\n"
        "**Goal**: Layered security against runaway loops and malicious imports\n"
    )
    assert "R1" not in rules(lint(source))


def test_hard_wrapped_long_sentence_still_warns_at_its_start(lint):
    source = (
        "Intro.\n\n"
        "Short one. We read the file and then we print it, we read the\n"
        "file and then we print it, and so we stop the run here now\n"
        "Python keeps going after that\n"
    )
    (w,) = [w for w in lint(source) if w.rule == "R1"]
    assert (w.line, w.col, w.message) == (
        3,
        12,
        "Sentence has 31 words; consider splitting.",
    )


# Rollout false positives (~/git/pp/prose-lint notes): verbs tagged as nouns.
@pytest.mark.parametrize(
    "source",
    [
        "- Test line number accuracy\n",
        "- Design word search grid:\n",
        "- Implement group CRUD endpoints\n",
        "- Checks notebook file existence\n",
        "- Purpose: Test database session management\n",
        "- `assert_valid()` - Validates crossword grid structure\n",
        "- ✅ Zero context overflow issues\n",
        "Theme follows the OS; a header toggle pins light/dark per viewer.",
        "The student progress bar resets after a logout.",
        "Agents never run under a repo: Claude Code loads ancestor CLAUDE.md files.",
        "Students reference error hints in their fixes.",
    ],
)
def test_noun_stack_skips_verbs_tagged_as_nouns(lint, source):
    assert "R2" not in rules(lint(source))


# Rollout false positives: a name plus a noun or two.
@pytest.mark.parametrize(
    "source",
    [
        "Explore and search your Claude Code conversation logs.",
        "You need a Google Cloud Platform account first.",
        "It sits beside the cache stats on the Cost Overview portfolio panel.",
    ],
)
def test_noun_stack_skips_proper_noun_compounds(lint, source):
    assert "R2" not in rules(lint(source))


def test_proper_noun_limit_is_configurable(lint):
    source = "Explore and search your Claude Code conversation logs."
    cfg = from_dict({"rules": {"noun-stack": {"max_proper_nouns": 2}}})
    assert "R2" in rules(lint(source, cfg))


# Rollout true positives that must stay flagged.
@pytest.mark.parametrize(
    ("source", "phrase"),
    [
        ("- Template type property verification\n", "Template type property"),
        ("- ✅ Maximum placement attempt limits\n", "Maximum placement attempt"),
        (
            "- 2 tests failing due to async context manager mocking complexity\n",
            "context manager mocking complexity",
        ),
        # The leading verb drops out; the four nouns after it still stack.
        (
            "- Implement Unicode character range analysis for language detection\n",
            '("Unicode character range analysis")',
        ),
    ],
)
def test_noun_stack_keeps_real_stacks(lint, source, phrase):
    (w,) = [w for w in lint(source) if w.rule == "R2"]
    assert phrase in w.message


# Rollout false positives: copula, counted things, plain verbs and hand-overs.
@pytest.mark.parametrize(
    "source",
    [
        "Positions are fractions of the panel.",
        "An **actor** is one placement of a character inside a panel.",
        "Cut every word that carries no information.",
        "This file provides guidance to Claude Code when working with code in "
        "this repository.",
        "Provide image descriptions or sources.",
        "Three exception handlers give every failure a visible representation.",
    ],
)
def test_nominalization_skips_plain_uses(lint, source):
    assert "R4" not in rules(lint(source))


@pytest.mark.parametrize(
    ("source", "phrase"),
    [
        (
            "The qa command performs one shared mutation.",
            "performs one shared mutation",
        ),
        ("We need to make a design decision.", "make a design decision"),
        ("Phase 1 is complete and provides a solid foundation.", "provides a solid"),
        ("The fix is the implementation of retries.", "is the implementation"),
    ],
)
def test_nominalization_keeps_hidden_verbs(lint, source, phrase):
    (w,) = [w for w in lint(source) if w.rule == "R4"]
    assert phrase in w.message


@pytest.mark.parametrize(
    "source",
    [
        "- Ensure the build passes\n",
        "- [ ] Ensure no visual regressions\n",
        "5. **Test contrast**: Ensure shapes are distinguishable\n",
        "The app starts successfully.",
        "Only show essential information.",
    ],
)
def test_habit_words_skip_checklist_ensure_and_plain_words(lint, source):
    assert "R3" not in rules(lint(source))


@pytest.mark.parametrize(
    ("source", "word"),
    [
        ("This pattern ensures correct initialization order.", "ensure"),
        ("- Ensures minimum gaps between obstacles\n", "ensure"),
        ("Phase 1 has been successfully implemented.", "successfully"),
        ("Successfully implemented the worksheet export.", "successfully"),
        ("It gives us a solid foundation for later work.", "solid foundation"),
    ],
)
def test_habit_words_catch_filler(lint, source, word):
    assert [w.message.split('"')[1] for w in lint(source) if w.rule == "R3"] == [word]


def test_item_start_exemption_is_configurable(lint):
    cfg = from_dict({"rules": {"habit-word": {"ok_at_item_start": []}}})
    assert "R3" in rules(lint("- Ensure the build passes\n", cfg))


KNOWN_BAD = Path(__file__).parent / "fixtures" / "known-bad.md"


def _known_bad_samples() -> list[tuple[str, str]]:
    """(rule id, sample) pairs: each sample follows a ``<!-- Rn -->`` marker."""
    parts = re.split(r"<!-- (R\d+) -->\n", KNOWN_BAD.read_text())
    return list(zip(parts[1::2], (p.strip() for p in parts[2::2]), strict=True))


def test_known_bad_file_covers_every_rule():
    assert sorted(rid for rid, _ in _known_bad_samples()) == sorted(RULES)


@pytest.mark.parametrize(("rid", "sample"), _known_bad_samples())
def test_each_rule_fires_on_its_known_bad_sample(lint, rid, sample):
    assert rid in rules(lint(sample))


def test_late_verb_counts_words_before_the_verb_group(lint):
    (w,) = [
        w
        for w in lint(
            "Every file that the old importer wrote to the shared folder during "
            "the nightly run last week has been deleted."
        )
        if w.rule == "R5"
    ]
    assert w.message.startswith('17 words before the main verb "has"')
    assert w.severity == "warning"


def test_late_verb_ignores_an_early_main_clause(lint):
    # The parser makes "checked" the root; "is" comes first.
    text = (
        "A version matrix on top of a flaky suite is noise, so the suite was "
        "checked for flakes before the matrix went in."
    )
    assert "R5" not in rules(lint(text))


def test_late_verb_restarts_after_a_label(lint):
    text = (
        "**Every nightly run of the importer on the shared folder**: the file is "
        "deleted."
    )
    assert "R5" not in rules(lint(text))


def test_late_verb_skips_fragments(lint):
    assert "R5" not in rules(lint("- The first of the three main reasons for it"))


def test_vague_this_needs_a_bare_pronoun_and_an_action_verb(lint):
    assert "R6" not in rules(lint("This flag allows faster lookups. It is fast."))
    assert "R6" not in rules(lint("This is the second stage. It is fast."))
    (w,) = [w for w in lint("This allows reuse. It is fast.") if w.rule == "R6"]
    assert (
        w.message
        == '"This allows": name what "this" is, or make the actor the subject.'
    )


def test_tidy_summary_only_at_paragraph_end(lint):
    assert "R7" not in rules(lint("Overall, it works. The cache is small."))
    assert "R7" not in rules(lint("Overall, it works."))
    (w,) = [w for w in lint("It caches. In short, it is fast.") if w.rule == "R7"]
    assert w.message.startswith('Paragraph ends with a summary ("In short ...")')


def test_closing_this_ensures_is_r7_not_r6(lint):
    found = rules(lint("The hook runs on commit. This ensures the docs stay clean."))
    assert "R7" in found
    assert "R6" not in found


def r8(warnings):
    return [(w.severity, w.message) for w in warnings if w.rule == "R8"]


def test_interruption_load_warns_at_two_and_is_strong_at_three(lint):
    two = "The cache \u2014 a plain dict \u2014 holds the parsed files."
    three = "The cache \u2014 a plain dict \u2014 holds files; nothing else is kept."
    assert r8(lint(two)) == [
        (
            "warning",
            "2 interruptions in one sentence (2 dashes); "
            "give each aside its own sentence.",
        )
    ]
    ((severity, message),) = r8(lint(three))
    assert severity == "strong"
    assert "(2 dashes, 1 semicolon)" in message


def test_interruption_load_allows_one_aside(lint):
    assert not r8(lint("The cache (a plain dict) holds the parsed files."))
    assert not r8(lint("The cache holds parsed files; nothing else is kept."))


def test_interruption_load_skips_label_separators(lint):
    # "`name` - description" and "**Label** - description" in list items.
    assert not r8(lint("- `name` \u2014 the symbol to find (as it is written)\n"))
    assert not r8(
        lint(
            "- **A loop of pure calls inside a test** \u2014 fixtures (functions "
            "that set things up) often loop.\n"
        )
    )
    assert not r8(lint("Note: the cache (a plain dict here) holds parsed files."))


def test_interruption_load_skips_short_glosses(lint):
    assert not r8(
        lint("Add `-d` (docs), `-r` (references), `-t` (test refs) or `--all`.")
    )


def test_interruption_load_skips_a_semicolon_that_ends_a_list_item(lint):
    assert not r8(
        lint("- private names: used by convention, or called by the interpreter;\n")
    )


def test_interruption_load_skips_a_colon_that_introduces_code(lint):
    assert not r8(lint("Run the build (it takes a minute or so) like this: `make`"))


def test_interruption_load_thresholds_are_configurable(lint):
    cfg = from_dict({"rules": {"interruption-load": {"warn_at": 3}}})
    assert not r8(lint("The cache \u2014 a plain dict \u2014 holds parsed files.", cfg))


def test_interruption_load_skips_marks_inside_quotes(lint):
    assert not r8(
        lint('It drops a verb that opens a line: "Purpose: Validates the grid" is one.')
    )
    assert not r8(
        lint('That means a recipient ("gives guidance to Claude Code") or a gift (x).')
    )


def r9(warnings):
    return [w for w in warnings if w.rule == "R9"]


CONTRASTS = (
    "# A report, not a gate\n\n"
    "The hook is an inventory, not a verdict.\n\n"
    "It lists findings rather than blocking the commit.\n"
)


def test_contrast_frame_reports_once_per_document_with_lines(lint):
    (w,) = r9(lint(CONTRASTS))
    assert (w.line, w.col) == (1, 11)  # the first frame, in the heading
    assert w.message.startswith('3 contrast frames such as "X, not Y"')
    assert "(lines 1, 3, 5)" in w.message


def test_contrast_frame_allows_a_few(lint):
    assert not r9(lint("The hook is an inventory, not a verdict. It never blocks."))


def test_contrast_frame_counts_a_negation_then_a_correction(lint):
    text = (
        "The exit code isn't a judgment. It's a count.\n\n"
        "The log isn't a report. It's a trace.\n\n"
        "The file is data, not code.\n"
    )
    (w,) = r9(lint(text))
    assert w.message.startswith("3 contrast frames")


def test_contrast_frame_scales_with_length(lint):
    # Three frames in a long document are below 4 per 1,000 words.
    filler = "The parser reads one file and then it writes one row. " * 80
    assert not r9(lint(CONTRASTS + "\n" + filler))
    cfg = from_dict({"rules": {"contrast-frame": {"max_per_1000": 1}}})
    assert r9(lint(CONTRASTS + "\n" + filler, cfg))


def test_contrast_frame_is_strong_at_twice_the_allowance(lint):
    text = "\n\n".join(f"Part {n} is data, not code." for n in range(5))
    (w,) = r9(lint(text))
    assert w.severity == "strong"


def test_contrast_frame_skips_plain_negation_and_additions(lint):
    # "not only X but also Y" adds; "does not X, but Y" concedes.
    adds = "It is not only fast but also small."
    concedes = "The run does not finish on a cold cache, but the next one does."
    assert not r9(lint("\n\n".join([adds] * 4)))
    assert not r9(lint("\n\n".join([concedes] * 4)))
    assert r9(lint("\n\n".join(["It is not a gate but a report."] * 4)))


def test_contrast_frame_leaves_out_disabled_blocks(lint):
    text = CONTRASTS.replace("It lists", "<!-- lepisma: disable-next R9 -->\nIt lists")
    assert not r9(lint(text))


def r10(warnings):
    return [w.message.split('"')[1] for w in warnings if w.rule == "R10"]


RARE = from_dict({"rules": {"undefined-term": {"rare_terms": True}}})


def test_undefined_term_flags_an_acronym_never_spelled_out(lint):
    (w,) = [
        w for w in lint("The daemon speaks LSP.\n\nLSP is fast.") if w.rule == "R10"
    ]
    assert (w.line, w.col) == (1, 19)  # the first use only
    assert w.message == (
        '"LSP" is never spelled out; write the full name at its first use, '
        'then "(LSP)".'
    )


def test_undefined_term_accepts_an_expansion_near_first_use(lint):
    assert not r10(lint("It speaks the Language Server Protocol (LSP)."))
    assert not r10(lint("It speaks LSP.\n\nLSP is the Language Server Protocol."))
    # Three blocks later is too late for the reader.
    late = "It speaks LSP.\n\nOne.\n\nTwo.\n\nThe Language Server Protocol."
    assert r10(lint(late)) == ["LSP"]


def test_undefined_term_skips_known_acronyms_common_words_and_code(lint):
    # API and JSON are on the known list; "path" is a common word; `LSP` is code.
    assert not r10(lint("The API returns JSON. Set PATH first. Run `LSP` now."))


def test_undefined_term_known_acronyms_are_configurable(lint):
    cfg = from_dict({"rules": {"R10": {"extra_known": ["lsp"]}}})
    assert not r10(lint("The daemon speaks LSP.", cfg))


def test_undefined_term_flags_a_rare_word_used_often_only_on_request(lint):
    text = "The worktree starts. Each worktree reads the config. A worktree then exits."
    assert not r10(lint(text))
    (w,) = [w for w in lint(text, RARE) if w.rule == "R10"]
    assert w.message.startswith('"worktree" appears 3 times and is never defined')


def test_undefined_term_accepts_a_definition(lint):
    uses = " Each worktree reads the config. One worktree then exits."
    for defined in (
        "A worktree is a second checkout.",
        "The second checkout (worktree) starts first.",
        "The checkout, called a worktree, starts first.",
        "The worktree, a second checkout, starts first.",
    ):
        assert not r10(lint(defined + uses, RARE)), defined


def test_undefined_term_skips_rare_words_that_are_names(lint):
    uses = "Then gerenuk reads the diff. Last, gerenuk picks the tests."
    # In the title, written as code elsewhere, or listed in known_terms.
    assert not r10(lint("# gerenuk\n\nFirst gerenuk starts. " + uses, RARE))
    assert not r10(lint("Run `gerenuk run`. First gerenuk starts. " + uses, RARE))
    cfg = from_dict(
        {"rules": {"R10": {"rare_terms": True, "known_terms": ["gerenuk"]}}}
    )
    assert not r10(lint("First gerenuk starts. " + uses, cfg))


def test_undefined_term_needs_min_uses_and_ignores_common_words(lint):
    assert not r10(lint("The worktree starts first. The worktree then exits.", RARE))
    common = "The cache starts. The cache fills. The cache is flushed and cached."
    assert not r10(lint(common, RARE))


def glossary_cfg(**extra):
    glossary = {
        "ADR": {"expansion": "Architecture Decision Record"},
        "worktree": {"definition": "A second checkout of the same repository."},
        "merge request": {"definition": "A proposed change."},
    }
    return from_dict({"rules": {"R10": {"glossary": glossary, **extra}}})


def test_undefined_term_skips_glossary_acronyms_and_their_plurals(lint):
    text = "Each ADR names one choice. Old ADRs stay. The daemon speaks LSP."
    assert r10(lint(text)) == ["ADR", "LSP"]
    assert r10(lint(text, glossary_cfg())) == ["LSP"]


def test_undefined_term_skips_glossary_terms_under_rare_terms(lint):
    text = "The worktree starts. Each worktree reads the config. A worktree then exits."
    assert r10(lint(text, RARE)) == ["worktree"]
    assert not r10(lint(text, glossary_cfg(rare_terms=True)))


def test_undefined_term_flags_a_gloss_that_differs_from_the_glossary(lint):
    cfg = glossary_cfg()
    for text in (
        "We wrote an Architectural Decision Report (ADR) for it.",
        "We wrote an ADR (Architectural Decision Report) for it.",
    ):
        (w,) = [w for w in lint(text, cfg) if w.rule == "R10"]
        assert w.message == (
            '"ADR" is glossed here as "Architectural Decision Report", but the '
            'glossary says "Architecture Decision Record"; use one name.'
        )
    assert lint("We wrote an ADR (Any Dumb Reason) for it.", cfg)[0].col == 13


def test_undefined_term_accepts_a_gloss_that_matches_the_glossary(lint):
    cfg = glossary_cfg()
    for text in (
        "We wrote an Architecture Decision Record (ADR) for it.",
        "We wrote an ADR (architecture-decision record) for it.",
        "We keep Architecture Decision Records (ADRs) here.",
        # Not a gloss: the words do not spell the acronym.
        "We wrote an ADR (see the next section) for it.",
    ):
        assert not r10(lint(text, cfg)), text


def test_undefined_term_spell_out_in_turns_the_glossary_off(nlp):
    cfg = glossary_cfg(spell_out_in=["README.md", "docs/public/*"])

    def flagged(path):
        return r10(lint_text(path, "Each ADR names one choice.", cfg, nlp).warnings)

    assert flagged("docs/adr.md") == []
    assert flagged("README.md") == ["ADR"]
    assert flagged("docs/public/intro.md") == ["ADR"]


def r11(warnings):
    return [w for w in warnings if w.rule == "R11"]


FIGURES = (
    "The seam between the two modules is narrow.\n\n"
    "Each seam has one owner.\n\n"
    "The verdict lands in the report.\n"
)


def test_emphasis_reports_figurative_terms_once_per_document(lint):
    (w,) = r11(lint(FIGURES))
    assert (w.line, w.col, w.severity) == (1, 5, "warning")
    assert w.message == (
        '4 figurative terms in this document ("seam" 2, "verdict" 1, "land" 1; '
        "lines 1, 3, 5); name the thing each one stands for, or define the term once."
    )


def test_emphasis_reports_sincerity_words_as_their_own_family(lint):
    text = (
        "It exactly matches the old output.\n\n"
        "The hook silently skips the file.\n\n"
        "That is genuinely useful.\n"
    )
    (w,) = r11(lint(text))
    assert w.message.startswith("3 sincerity words in this document")
    assert w.message.endswith("cut each one, or state the fact that backs it.")


def test_emphasis_counts_each_family_on_its_own(lint):
    # Two of one family and two of the other: neither reaches three.
    text = (
        "The seam is narrow. The verdict is final. It exactly fits. It is quietly on."
    )
    assert not r11(lint(text))


def test_emphasis_allows_a_few_and_scales_with_length(lint):
    assert not r11(lint("The seam between the modules is narrow. Each seam is small."))
    filler = "The parser reads one file and then it writes one row. " * 140
    assert not r11(lint(FIGURES + "\n" + filler))


def test_emphasis_skips_a_term_the_document_introduces(lint):
    named = "A seam is the one place where a module spawns a process.\n\n"
    assert not r11(lint(named + FIGURES.replace("The verdict lands", "The result is")))


def test_emphasis_skips_code_and_disabled_blocks(lint):
    three = "The seam is narrow.\n\nEach seam has one owner.\n\nA seam is small.\n"
    assert not r11(lint("Seams matter.\n\n" + three))  # "A seam is" names it
    plain = three.replace("A seam is small.", "No seam is wide.")
    assert r11(lint(plain))
    assert not r11(lint(plain.replace("Each seam", "Each `seam`")))
    off = plain.replace("Each seam", "<!-- lepisma: disable-next R11 -->\nEach seam")
    assert not r11(lint(off))


def test_emphasis_lists_are_configurable(lint):
    cfg = from_dict({"rules": {"emphasis": {"figurative": ["pipeline"]}}})
    assert not r11(lint(FIGURES, cfg))
    text = "The pipeline runs. The pipeline stops. The pipeline restarts."
    assert r11(lint(text, cfg))


def test_emphasis_is_strong_at_twice_the_allowance(lint):
    (w,) = r11(lint(FIGURES + "\nA load-bearing seam.\n"))
    assert w.severity == "strong"
