import pytest

from prose_lint.config import Config, from_dict
from prose_lint.rules import verb_form


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
    text = "<!-- prose-lint: disable R3 -->\nWe leverage it.\n"
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
