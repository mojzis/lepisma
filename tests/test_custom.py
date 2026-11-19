import pytest

from lepisma.config import PROFILES, ConfigError, from_dict
from lepisma.report import print_stats

PASSIVE = {"message": 'Passive ("{match} {head}").', "pattern": [{"DEP": "auxpass"}]}


def custom(**rules):
    return from_dict({"rules": {"R3": {"enabled": False}}, "custom": rules})


def test_a_pattern_rule_reports_its_own_name_and_message(lint):
    (w,) = lint("The file is deleted by the server.", custom(passive=PASSIVE))
    assert (w.rule, w.name, w.severity) == ("passive", "passive", "warning")
    assert (w.line, w.col) == (1, 10)
    assert w.message == 'Passive ("is deleted").'


def test_words_match_forms_lemmas_and_phrases(lint):
    rule = {"message": 'Say "{match}" plainly.', "words": ["Leverage", "kick off"]}
    found = lint("We leveraged it. Kick off the build.", custom(plain=rule))
    assert [w.message for w in found] == [
        'Say "leveraged" plainly.',
        'Say "Kick off" plainly.',
    ]


def test_several_patterns_and_severity(lint):
    rule = {
        "message": "No {lemma}.",
        "severity": "strong",
        "pattern": [[{"LOWER": "foo"}], [{"LOWER": "bar"}, {"LOWER": "baz"}]],
    }
    found = lint("A foo and a bar baz.", custom(nope=rule))
    assert [(w.message, w.severity) for w in found] == [
        ("No foo.", "strong"),
        ("No bar baz.", "strong"),
    ]


def test_allow_skips_a_match_by_text_or_by_head(lint):
    rule = {
        "message": 'Phrasal verb "{head} {match}".',
        "pattern": [{"DEP": "prt"}],
        "allow": ["Set up"],
    }
    found = lint("Take it out. Then set up the server.", custom(phrasal=rule))
    assert [w.message for w in found] == ['Phrasal verb "Take out".']


def test_custom_rules_skip_code_and_headings(lint):
    cfg = custom(nofoo={"message": "No foo.", "words": ["foo"]})
    assert lint("# Foo\n\nSet `foo` here.\n", cfg) == []
    assert len(lint("Set foo here.", cfg)) == 1


def test_disable_comments_cover_custom_rules(lint):
    cfg = custom(nofoo={"message": "No foo.", "words": ["foo"]})
    by_name = "<!-- lepisma: disable-next nofoo -->\nA foo.\n\nA foo.\n"
    assert [w.line for w in lint(by_name, cfg)] == [4]
    assert lint("<!-- lepisma: disable -->\nA foo.\n", cfg) == []
    other = "<!-- lepisma: disable-next R1 -->\nA foo.\n"
    assert len(lint(other, cfg)) == 1


def test_a_disabled_custom_rule_is_silent(lint):
    rule = {"message": "No foo.", "words": ["foo"], "enabled": False}
    assert lint("A foo.", custom(nofoo=rule)) == []


def test_a_pattern_spacy_rejects_is_a_config_error(lint):
    bad = {"message": "x", "pattern": [{"NO_SUCH_ATTR": "x"}]}
    with pytest.raises(ConfigError, match=r"\[custom\.bad\] bad pattern"):
        lint("Any text.", custom(bad=bad))


@pytest.mark.parametrize(
    "rule",
    [
        {"pattern": [{"LOWER": "x"}]},  # no message
        {"message": "x"},  # nothing to match
        {"message": "x", "pattern": []},
        {"message": "x", "pattern": ["will"]},
        {"message": "x", "words": "foo"},
        {"message": "x", "words": ["foo"], "severity": "fatal"},
        {"message": "x", "words": ["foo"], "enabled": "yes"},
        {"message": "x", "words": ["foo"], "bogus": 1},
        "not a table",
    ],
)
def test_invalid_custom_rule_raises(rule):
    with pytest.raises(ConfigError):
        from_dict({"custom": {"mine": rule}})


@pytest.mark.parametrize("name", ["R1", "noun-stack", "Mine", "has space", "9lives"])
def test_custom_rule_name_must_be_new_and_lowercase(name):
    with pytest.raises(ConfigError):
        from_dict({"custom": {name: {"message": "x", "words": ["foo"]}}})


def test_profile_sets_rules_and_the_config_wins():
    cfg = from_dict(
        {
            "profile": "ste",
            "rules": {
                "R1": {"instruction_max_words": 18},
                "ing-word": {"enabled": False},
            },
            "custom": {
                "phrasal-verb": {"allow": ["look up"]},
                "passive-voice": {"enabled": False},
                "mine": {"message": "x", "words": ["foo"]},
            },
        }
    )
    assert cfg.long_sentence.instruction_max_words == 18
    assert cfg.long_paragraph.enabled
    assert not cfg.ing_word.enabled
    by_name = {rule.name: rule for rule in cfg.custom}
    assert by_name["phrasal-verb"].allow == ["look up"]
    assert by_name["phrasal-verb"].patterns == [[{"DEP": "prt"}]]
    assert not by_name["passive-voice"].enabled
    assert "mine" in by_name
    assert "contraction" in by_name


def test_profile_is_not_changed_by_a_config():
    before = repr(PROFILES)
    from_dict({"profile": "ste", "custom": {"phrasal-verb": {"allow": []}}})
    assert repr(PROFILES) == before


def test_unknown_profile_raises():
    with pytest.raises(ConfigError, match="unknown profile"):
        from_dict({"profile": "nope"})


STE_DOC = """\
Don't utilize the old key. The user's file is deleted by the server.
Take out the old key and set up the server. Wait five minutes.

The server has started. It is running now. The first one is good.
"""


def test_ste_profile_flags_each_pattern_once(lint):
    found = lint(STE_DOC, from_dict({"profile": "ste"}))
    assert [(w.line, w.rule, w.message.split('"')[1]) for w in found] == [
        (1, "contraction", "n't"),
        (1, "R3", "utilize"),
        (1, "passive-voice", "is deleted"),
        (2, "phrasal-verb", "Take out"),
        (2, "number-word", "five"),
        (4, "perfect-tense", "has started"),
        (4, "progressive-tense", "is running"),
    ]


def test_ste_profile_is_quiet_on_plain_text(lint):
    plain = (
        "Stop the server before you remove the disk. The server writes 3 files. "
        "It does not delete the old key. The user's file stays there."
    )
    assert lint(plain, from_dict({"profile": "ste"})) == []


def test_stats_sum_custom_rules_in_one_column(nlp, capsys):
    from lepisma.engine import lint_text  # noqa: PLC0415

    cfg = custom(nofoo={"message": "No foo.", "words": ["foo"]})
    result = lint_text("doc.md", "A foo and a foo here.", cfg, nlp)
    print_stats({"docs": [result]})
    lines = capsys.readouterr().out.splitlines()
    assert lines[2].split()[-1] == "cust"
    assert float(lines[3].split()[-1]) > 0
