"""Local FastAPI server that keeps the spaCy model loaded between commits."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from prose_lint import __version__
from prose_lint.config import ConfigError, from_dict
from prose_lint.engine import lint_text, load_nlp
from prose_lint.models import FileResult

CACHE_SIZE = 512
IDLE_CHECK_S = 60


class SourceFile(BaseModel):
    """One file to lint."""

    path: str
    text: str


class LintRequest(BaseModel):
    """Files plus the repo's raw ``prose-lint.toml`` contents."""

    files: list[SourceFile]
    config: dict[str, Any] = {}


class _Cache:
    """Small LRU of results keyed by file text and config, so re-commits are free."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.items: OrderedDict[str, FileResult] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key: str) -> FileResult | None:
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
        return None

    def put(self, key: str, value: FileResult) -> None:
        with self.lock:
            self.items[key] = value
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)


def create_app(on_shutdown: threading.Event | None = None) -> FastAPI:
    """Build the app. ``on_shutdown`` is set when a client asks the server to stop."""
    app = FastAPI(title="prose-lint")
    cache = _Cache(CACHE_SIZE)
    app.state.last_request = time.monotonic()

    @app.get("/health")
    def health() -> dict[str, str]:
        app.state.last_request = time.monotonic()
        return {"status": "ok", "version": __version__}

    @app.post("/lint")
    def lint(req: LintRequest) -> dict[str, Any]:
        app.state.last_request = time.monotonic()
        try:
            cfg = from_dict(req.config)
        except ConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        cfg_key = json.dumps(req.config, sort_keys=True, default=str)
        nlp = load_nlp()
        results = []
        for f in req.files:
            key = hashlib.sha256(f"{cfg_key}\0{f.path}\0{f.text}".encode()).hexdigest()
            result = cache.get(key)
            if result is None:
                result = lint_text(f.path, f.text, cfg, nlp)
                cache.put(key, result)
            results.append(result.to_dict())
        return {"version": __version__, "results": results}

    @app.post("/shutdown")
    def shutdown() -> dict[str, str]:
        if on_shutdown is not None:
            on_shutdown.set()
        return {"status": "stopping"}

    return app


def serve(port: int, idle_timeout_s: int) -> None:
    """Run until idle for ``idle_timeout_s`` seconds or asked to shut down."""
    load_nlp()  # load before binding, so /health means "ready"
    stop = threading.Event()
    app = create_app(stop)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )

    def watchdog() -> None:
        if idle_timeout_s <= 0:
            return
        while not stop.wait(min(IDLE_CHECK_S, idle_timeout_s)):
            if time.monotonic() - app.state.last_request > idle_timeout_s:
                stop.set()

    def stop_watcher() -> None:
        stop.wait()
        server.should_exit = True

    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=stop_watcher, daemon=True).start()
    server.run()
