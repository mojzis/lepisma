import pytest

from lepisma.config import ConfigError, find_config, from_dict, load_raw, rule_id


def test_overrides_and_rule_names():
    cfg = from_dict(
        {
            "ignore": ["CHANGELOG.md", "vendor/*"],
            "rules": {"R1": {"max_words": 30}, "noun-stack": {"min_nouns": 4}},
            "server": {"timeout_ms": 500},
        }
    )
    assert cfg.long_sentence.max_words == 30
    assert cfg.noun_stack.min_nouns == 4
    assert cfg.server.timeout_ms == 500
    assert cfg.is_ignored("vendor/lib/README.md")
    assert cfg.is_ignored("notes.txt")
    assert not cfg.is_ignored("docs/guide.md")


def test_habit_word_list_replace_extend_and_suggest():
    cfg = from_dict(
        {
            "rules": {
                "R3": {
                    "words": ["robust"],
                    "extra_words": ["paradigm"],
                    "suggestions": {"paradigm": "model"},
                }
            }
        }
    )
    assert cfg.habit_words.words == {"robust": "", "paradigm": "model"}


def test_extra_stoplist_extends_defaults():
    cfg = from_dict({"rules": {"R4": {"extra_stoplist": ["Migration"]}}})
    assert "migration" in cfg.nominalization.stoplist
    assert "function" in cfg.nominalization.stoplist


@pytest.mark.parametrize(
    "data",
    [
        {"rules": {"R99": {}}},
        {"rules": {"R1": {"max_wordz": 3}}},
        {"rules": {"R1": {"max_words": "many"}}},
        {"rules": {"R1": {"enabled": 1}}},
        {"bogus": 1},
        {"ignore": "x"},
    ],
)
def test_invalid_config_raises(data):
    with pytest.raises(ConfigError):
        from_dict(data)


def test_rule_id_lookup():
    assert rule_id("r2") == "R2"
    assert rule_id("habit-word") == "R3"
    assert rule_id("nope") is None


def test_find_and_load_walk_up(tmp_path):
    (tmp_path / "lepisma.toml").write_text("[rules.R1]\nmax_words = 20\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_config(nested) == tmp_path / "lepisma.toml"
    assert load_raw(nested) == {"rules": {"R1": {"max_words": 20}}}
