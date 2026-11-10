import socket
import subprocess

import pytest

from prose_lint import client
from prose_lint.client import Skip, lint_via_server, run_hook


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
    monkeypatch.setenv("PROSE_LINT_PORT", str(free_port()))
    assert run_hook() == 0
    assert capsys.readouterr() == ("", "")
    assert len(spawned) == 1


def test_disable_env_skips_everything(repo, monkeypatch):
    monkeypatch.setenv("PROSE_LINT_DISABLE", "1")
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
    assert out[1].startswith("prose-lint: 1 warning(s) in 1 file(s)")


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
