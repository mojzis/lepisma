import json
import subprocess

from lepisma.cli import HOOK_MARKER, main


def test_check_text(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("We utilize it.\n")
    assert main(["check", "a.md"]) == 0
    assert capsys.readouterr().out == 'a.md:1:4 R3 Habit word "utilize"; try: use.\n'


def test_check_json_strict(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("We utilize it.\n")
    assert main(["check", "--format", "json", "--strict", "."]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["warnings"] == 1
    assert data["warnings"][0]["name"] == "habit-word"


def test_check_respects_ignore(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lepisma.toml").write_text('ignore = ["skip/*"]\n')
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "a.md").write_text("We utilize it.\n")
    assert main(["check", "--strict", "."]) == 0
    assert capsys.readouterr().out == ""


def test_stats_prints_groups(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("We utilize it.\n")
    main(["stats", "."])
    out = capsys.readouterr().out
    assert "== ." in out
    assert "TOTAL" in out


def test_install_hook_prepends_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexec other-hook\n")
    assert main(["install-hook"]) == 0
    assert main(["install-hook"]) == 0
    first, ours, rest = hook.read_text().splitlines()
    assert (first, rest) == ("#!/bin/sh", "exec other-hook")
    assert HOOK_MARKER in ours


def test_check_glossary_flag_layers_after_the_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lepisma.toml").write_text('[rules.R10]\nglossary = ["org.toml"]\n')
    (tmp_path / "org.toml").write_text('[ADR]\nexpansion = "Any Decision Record"\n')
    (tmp_path / "repo.toml").write_text(
        '[ADR]\nexpansion = "Architecture Decision Record"\n'
        '[LSP]\nexpansion = "Language Server Protocol"\n'
    )
    (tmp_path / "a.md").write_text(
        "Each ADR names one choice. The daemon speaks LSP.\n"
    )
    main(["check", "a.md"])
    assert capsys.readouterr().out.startswith('a.md:1:46 R10 "LSP" is never spelled')
    main(["check", "--glossary", "repo.toml", "a.md"])
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith('lepisma: glossary conflict for "ADR"')


def test_hook_passes_glossary_flags_to_the_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "lepisma.client.run_hook", lambda files, **kw: seen.update(kw) or 0
    )
    assert main(["hook", "--glossary", "a.toml", "--glossary", "b.toml"]) == 0
    assert seen["glossaries"] == ["a.toml", "b.toml"]
