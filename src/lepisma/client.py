"""Commit hook client. Stdlib only: it must start fast and never block a commit.

Sends staged Markdown files to the local server and prints the warnings. When the
server is down it starts one in the background and skips this commit; when the
server is slow it skips. Every failure path is silent unless
``LEPISMA_VERBOSE=1``.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from lepisma import build_id
from lepisma.config import ConfigError, from_dict, load_raw
from lepisma.models import FileResult

SPAWN_COOLDOWN_S = 30
DEFAULT_IDLE_TIMEOUT_S = 4 * 3600


class Skip(Exception):
    """Raised to skip quietly (fail open)."""


def _verbose() -> bool:
    return os.environ.get("LEPISMA_VERBOSE") == "1"


def note(msg: str) -> None:
    """Print a diagnostic to stderr, only in verbose mode."""
    if _verbose():
        print(f"lepisma: {msg}", file=sys.stderr)  # noqa: T201


def cache_dir() -> Path:
    """Directory for the server log and spawn stamp."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    path = Path(base) / "lepisma"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _git(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["git", *args],  # noqa: S607 - git from PATH, as every hook does
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    return out.stdout


def staged_files(root: Path, cfg_extensions: list[str]) -> list[str]:
    """Paths (relative to the repo root) of staged, added or modified docs."""
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", cwd=root)
    return [
        p for p in out.split("\0") if p and Path(p).suffix.lower() in cfg_extensions
    ]


def staged_text(root: Path, path: str) -> str:
    """The staged (index) version of ``path``, so line numbers match the commit."""
    return _git("show", f":{path}", cwd=root)


def _url(port: int, route: str) -> str:
    return f"http://127.0.0.1:{port}{route}"


def post(port: int, route: str, payload: dict[str, Any], timeout_s: float) -> Any:
    """POST JSON to the local server and return the decoded reply."""
    req = urllib.request.Request(  # noqa: S310 - fixed http://127.0.0.1 URL
        _url(port, route),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        return json.loads(resp.read())


def healthy(port: int, timeout_s: float = 0.2) -> bool:
    """True when a lepisma server answers on ``port``."""
    try:
        with urllib.request.urlopen(_url(port, "/health"), timeout=timeout_s) as resp:  # noqa: S310
            return json.loads(resp.read()).get("status") == "ok"
    except (OSError, ValueError):
        return False


def spawn_server(port: int, *, force: bool = False) -> bool:
    """Start the server in the background. False when one was started recently."""
    stamp = cache_dir() / f"spawn-{port}"
    recent = stamp.exists() and time.time() - stamp.stat().st_mtime < SPAWN_COOLDOWN_S
    if recent and not force:
        return False
    stamp.touch()
    log = (cache_dir() / "server.log").open("ab")
    subprocess.Popen(  # noqa: S603 - our own interpreter and module
        [sys.executable, "-m", "lepisma", "serve", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )
    return True


def lint_via_server(
    files: list[tuple[str, str]], raw_cfg: dict[str, Any], port: int, timeout_s: float
) -> list[FileResult]:
    """Lint through the server, raising Skip on any failure."""
    try:
        reply = post(
            port,
            "/lint",
            {"files": [{"path": p, "text": t} for p, t in files], "config": raw_cfg},
            timeout_s,
        )
    except urllib.error.HTTPError as exc:
        raise Skip(
            f"server error {exc.code}: {exc.read().decode(errors='replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            started = spawn_server(port)
            raise Skip(
                "server not running; "
                + ("starting it" if started else "it is starting")
            ) from exc
        raise Skip(f"server unreachable ({exc.reason})") from exc
    except (TimeoutError, OSError) as exc:
        raise Skip(f"server too slow (>{timeout_s * 1000:.0f} ms)") from exc
    current = build_id()
    if reply.get("version") != current:
        # The server runs older code: its results may be wrong. Replace it and skip.
        # The new server loads spaCy before it binds, so the old one is gone by then.
        with contextlib.suppress(OSError):
            post(port, "/shutdown", {}, 0.2)
        spawn_server(port, force=True)
        raise Skip(f"server ran {reply.get('version')}, restarting as {current}")
    return [FileResult.from_dict(r) for r in reply["results"]]


def wait_for_server(port: int, wait_s: float) -> None:
    """Start the server if needed and block until it is healthy or ``wait_s`` passes."""
    if healthy(port):
        return
    spawn_server(port)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if healthy(port):
            return
        time.sleep(0.1)
    raise Skip(f"server did not start within {wait_s:.0f} s")


def read_staged(root: Path, path: str) -> str:
    """Staged text of ``path``; the working copy when it is not in the index."""
    try:
        return staged_text(root, path)
    except subprocess.CalledProcessError:
        return (root / path).read_text(encoding="utf-8")


def run_hook(
    files: list[str] | None = None, *, fmt: str = "text", wait_s: float = 0.0
) -> int:
    """Entry point for the pre-commit hook. Always returns 0.

    ``files`` are paths relative to the repo root, as madoqua passes them. Without
    them the hook asks git for the staged docs itself.
    """
    if os.environ.get("LEPISMA_DISABLE") == "1":
        return 0
    try:
        root = Path(_git("rev-parse", "--show-toplevel").strip())
        raw_cfg = load_raw(root)
        cfg = from_dict(raw_cfg)
        candidates = files if files else staged_files(root, cfg.extensions)
        paths = [p for p in candidates if not cfg.is_ignored(p)]
        if not paths:
            return 0
        port = int(os.environ.get("LEPISMA_PORT", cfg.server.port))
        timeout_ms = int(os.environ.get("LEPISMA_TIMEOUT_MS", cfg.server.timeout_ms))
        if wait_s > 0:
            wait_for_server(port, wait_s)
        docs = [(p, read_staged(root, p)) for p in paths]
        results = lint_via_server(docs, raw_cfg, port, timeout_ms / 1000)
    except Skip as exc:
        note(f"skipped: {exc}")
        return 0
    except (ConfigError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        note(f"skipped: {exc}")
        return 0
    from lepisma.report import print_results  # noqa: PLC0415 - keep startup lean

    print_results(results, fmt, footer=True)
    return 0
