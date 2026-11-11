import pytest

from lepisma.config import (
    ConfigError,
    find_config,
    from_dict,
    load_raw,
    read_glossary,
    rule_id,
)


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


ADR = '[ADR]\nexpansion = "Architecture Decision Record"\n'


def glossary_of(raw):
    return raw["rules"]["undefined-term"]["glossary"]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("[ADR\n", r"g\.toml: invalid TOML"),
        ("[ADR]\n", r"g\.toml: \[ADR\] needs an expansion or a definition"),
        ("[ADR]\nexpansion = 3\n", r"g\.toml: \[ADR\] expansion must be a string"),
        ("[ADR]\ndefinition = ['x']\n", r"\[ADR\] definition must be a string"),
        ("[ADR]\nmeaning = 'x'\n", r"\[ADR\] has unknown field\(s\): meaning"),
        ("ADR = 'x'\n", r"g\.toml: \[ADR\] must be a table"),
    ],
)
def test_bad_glossary_is_reported_and_left_out(tmp_path, capsys, body, error):
    path = tmp_path / "g.toml"
    path.write_text(body)
    with pytest.raises(ConfigError, match=error):
        read_glossary(path)
    (tmp_path / "ok.toml").write_text(ADR)
    raw = load_raw(tmp_path, [path, tmp_path / "ok.toml"])
    assert list(glossary_of(raw)) == ["ADR"]  # the good file still loads
    err = capsys.readouterr().err
    assert err.startswith("lepisma: glossary skipped: ")
    assert "g.toml" in err


def test_missing_glossary_is_reported_and_left_out(tmp_path, capsys):
    with pytest.raises(ConfigError, match=r"g\.toml: cannot read glossary"):
        read_glossary(tmp_path / "g.toml")
    raw = load_raw(tmp_path, [tmp_path / "g.toml"])
    assert glossary_of(raw) == {}
    assert "glossary skipped" in capsys.readouterr().err


def test_glossary_layers_and_reports_changed_expansions(tmp_path, capsys):
    (tmp_path / "org.toml").write_text(
        ADR + 'definition = "Org text."\n[MR]\nexpansion = "merge request"\n'
    )
    (tmp_path / "repo.toml").write_text(
        '[ADR]\nexpansion = "Any Decision Record"\n'
        '[MR]\nexpansion = "merge request"\n'
        '[worktree]\ndefinition = "A second checkout."\n'
    )
    raw = load_raw(tmp_path, [tmp_path / "org.toml", tmp_path / "repo.toml"])
    assert glossary_of(raw) == {
        "ADR": {"expansion": "Any Decision Record", "definition": "Org text."},
        "MR": {"expansion": "merge request"},
        "worktree": {"definition": "A second checkout."},
    }
    (line,) = capsys.readouterr().err.splitlines()  # the identical MR is silent
    assert line == (
        'lepisma: glossary conflict for "ADR": "Any Decision Record" from '
        f'{tmp_path / "repo.toml"} replaces "Architecture Decision Record" from '
        f"{tmp_path / 'org.toml'}"
    )


def test_glossary_paths_resolve_from_config_dir_then_cwd(tmp_path, monkeypatch):
    (tmp_path / "lepisma.toml").write_text(
        '[rules.R10]\nglossary = ["shared/org.toml"]\n'
    )
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "org.toml").write_text(ADR)
    nested = tmp_path / "docs"
    nested.mkdir()
    (nested / "local.toml").write_text('[ADR]\ndefinition = "Local."\n')
    monkeypatch.chdir(nested)
    raw = load_raw(nested, ["local.toml"])
    assert raw == {
        "rules": {
            "R10": {
                "glossary": {
                    "ADR": {
                        "expansion": "Architecture Decision Record",
                        "definition": "Local.",
                    }
                }
            }
        }
    }


def test_no_glossary_leaves_the_raw_config_alone(tmp_path):
    (tmp_path / "lepisma.toml").write_text("[rules.R10]\nmin_uses = 4\n")
    assert load_raw(tmp_path) == {"rules": {"R10": {"min_uses": 4}}}
    assert from_dict({}).undefined_term.glossary == {}


def test_from_dict_takes_the_glossary_inline():
    entries = {"ADR": {"expansion": "Architecture Decision Record"}}
    cfg = from_dict(
        {"rules": {"R10": {"glossary": entries, "spell_out_in": ["README.md"]}}}
    )
    assert cfg.undefined_term.glossary == entries
    assert cfg.spells_out("README.md")
    assert not cfg.spells_out("docs/README.md")


@pytest.mark.parametrize(
    "glossary", [["org.toml"], {"ADR": {}}, {"ADR": {"expansion": 1}}, {"ADR": "x"}]
)
def test_from_dict_rejects_a_bad_inline_glossary(glossary):
    with pytest.raises(ConfigError, match="glossary"):
        from_dict({"rules": {"R10": {"glossary": glossary}}})
