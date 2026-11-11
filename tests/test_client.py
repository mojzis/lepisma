import socket
import subprocess

import pytest

from lepisma import client
from lepisma.client import Skip, lint_via_server, run_hook


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "doc.md").write_text("We leverage it.\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], check=True)
    return tmp_path


def test_staged_files_filters_by_extension(repo):
    assert client.staged_files(repo, [".md"]) == ["doc.md"]


def test_no_server_starts_one_and_skips_quietly(repo, monkeypatch, capsys):
    spawned = []
    monkeypatch.setattr(
        client, "spawn_server", lambda port: spawned.append(port) or True
    )
    monkeypatch.setenv("LEPISMA_PORT", str(free_port()))
    assert run_hook() == 0
    assert capsys.readouterr() == ("", "")
    assert len(spawned) == 1


def test_explicit_files_skip_git_discovery(repo, monkeypatch):
    sent = []
    monkeypatch.setattr(client, "staged_files", lambda *a: pytest.fail("asked git"))
    monkeypatch.setattr(
        client, "lint_via_server", lambda docs, *a: sent.extend(docs) or []
    )
    (repo / "notes.md").write_text("Unstaged.\n")
    assert run_hook(["doc.md", "notes.md", "code.py"]) == 0
    assert sent == [("doc.md", "We leverage it.\n"), ("notes.md", "Unstaged.\n")]


def test_disable_env_skips_everything(repo, monkeypatch):
    monkeypatch.setenv("LEPISMA_DISABLE", "1")
    monkeypatch.setattr(client, "staged_files", lambda *a: pytest.fail("ran"))
    assert run_hook() == 0


def test_slow_server_is_skipped(monkeypatch):
    def slow(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(client, "post", slow)
    with pytest.raises(Skip, match="too slow"):
        lint_via_server([("a.md", "x")], {}, 1, 0.3)


def test_results_are_printed(repo, monkeypatch, capsys):
    reply = {
        "version": client.build_id(),
        "results": [
            {
                "path": "doc.md",
                "words": 3,
                "warnings": [
                    {
                        "path": "doc.md",
                        "line": 1,
                        "col": 4,
                        "rule": "R3",
                        "name": "habit-word",
                        "severity": "warning",
                        "message": 'Habit word "leverage"; try: use.',
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(client, "post", lambda *a, **k: reply)
    assert run_hook() == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'doc.md:1:4 R3 Habit word "leverage"; try: use.'
    assert out[1].startswith("lepisma: 1 warning(s) in 1 file(s)")


def test_stale_server_is_replaced_and_skipped(monkeypatch):
    calls = []

    def fake_post(port, route, payload, timeout_s):
        calls.append(route)
        return {"version": "0.0.1+old", "results": []}

    monkeypatch.setattr(client, "post", fake_post)
    monkeypatch.setattr(
        client, "spawn_server", lambda port, force: calls.append("spawn")
    )
    with pytest.raises(Skip, match="restarting"):
        lint_via_server([("a.md", "x")], {}, 1, 0.3)
    assert calls == ["/lint", "/shutdown", "spawn"]


def test_spawn_has_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    started = []
    monkeypatch.setattr(client.subprocess, "Popen", lambda *a, **k: started.append(a))
    assert client.spawn_server(1234) is True
    assert client.spawn_server(1234) is False
    assert len(started) == 1


def test_hook_inlines_glossaries_into_the_posted_config(repo, monkeypatch):
    (repo / "lepisma.toml").write_text('[rules.R10]\nglossary = ["org.toml"]\n')
    (repo / "org.toml").write_text(
        '[ADR]\nexpansion = "Architecture Decision Record"\n'
    )
    (repo / "extra.toml").write_text('[worktree]\ndefinition = "A second checkout."\n')
    sent = []
    monkeypatch.setattr(
        client, "lint_via_server", lambda docs, raw, *a: sent.append(raw) or []
    )
    assert run_hook(glossaries=["extra.toml"]) == 0
    assert sent == [
        {
            "rules": {
                "R10": {
                    "glossary": {
                        "ADR": {"expansion": "Architecture Decision Record"},
                        "worktree": {"definition": "A second checkout."},
                    }
                }
            }
        }
    ]


@pytest.mark.parametrize("config", ['glossary = ["bad.toml"]', "glossary = 3"])
def test_bad_glossary_leaves_the_hook_at_exit_zero(repo, monkeypatch, capsys, config):
    (repo / "lepisma.toml").write_text(f"[rules.R10]\n{config}\n")
    (repo / "bad.toml").write_text("[ADR]\nexpansion = 3\n")
    monkeypatch.setattr(client, "lint_via_server", lambda *a: [])
    assert run_hook(glossaries=["missing.toml"]) == 0
    assert capsys.readouterr().out == ""
