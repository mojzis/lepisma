"""Find the spaCy model, downloading it into the user cache on first use.

spaCy models are not on PyPI, so the package cannot depend on one. An installed
``en_core_web_sm`` package wins (dev installs, offline ``uv pip install``).
Otherwise the pinned wheel is fetched once, checked against its SHA-256, and
unpacked under ``~/.cache/lepisma/models``; spaCy then loads it by path.

This needs no pip and never writes into the Python environment, so it works the
same under ``uvx``, ``uv tool install`` and a plain venv, and the cache outlives
uvx's throwaway environments. Stdlib only: the server and ``check`` call it before
importing spaCy, and the hook client never calls it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from lepisma.client import cache_dir

MODEL = "en_core_web_sm"
VERSION = "3.8.0"  # keep on the spaCy minor in pyproject (spacy>=3.8,<3.9)
WHEEL_URL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    f"{MODEL}-{VERSION}/{MODEL}-{VERSION}-py3-none-any.whl"
)
WHEEL_SHA256 = "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
# A local path or URL to fetch the same wheel from, e.g. for offline machines.
WHEEL_ENV = "LEPISMA_MODEL_WHEEL"
DOWNLOAD_TIMEOUT_S = 60


class ModelError(RuntimeError):
    """The model is not installed and could not be downloaded."""


def model_dir() -> Path:
    """Where the unpacked wheel lives; spaCy loads the data folder inside it."""
    return cache_dir() / "models" / f"{MODEL}-{VERSION}"


def _data_path(root: Path) -> Path:
    return root / MODEL / f"{MODEL}-{VERSION}"


def _fetch(source: str) -> bytes:
    if source.startswith(("https://", "http://")):
        with urllib.request.urlopen(source, timeout=DOWNLOAD_TIMEOUT_S) as resp:  # noqa: S310 - scheme checked
            return resp.read()
    return Path(source).expanduser().read_bytes()


def download(root: Path) -> None:
    """Fetch the wheel, check its hash and unpack it to ``root`` atomically."""
    source = os.environ.get(WHEEL_ENV) or WHEEL_URL
    print(  # noqa: T201
        f"lepisma: downloading spaCy model {MODEL} (~13 MB, once)…",
        file=sys.stderr,
        flush=True,
    )
    try:
        data = _fetch(source)
    except OSError as exc:
        raise ModelError(
            f"could not fetch {source}: {exc}. Offline? Install the model with "
            f"`uv pip install {WHEEL_URL}`, or set {WHEEL_ENV} to a local copy "
            "of that wheel."
        ) from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != WHEEL_SHA256:
        raise ModelError(f"{source} has SHA-256 {digest}, expected {WHEEL_SHA256}")
    root.parent.mkdir(parents=True, exist_ok=True)
    # Unpack beside the target and rename, so a crash or a second process never
    # leaves a half-written model where the next run would load it.
    tmp = Path(tempfile.mkdtemp(prefix=f".{root.name}-", dir=root.parent))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            wheel.extractall(tmp)
        try:
            tmp.rename(root)
        except OSError:
            if not _data_path(root).is_dir():  # not a lost race: a real failure
                raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def locate() -> str | Path:
    """What to pass to ``spacy.load``: the package name, or the cached model path."""
    if importlib.util.find_spec(MODEL) is not None:
        return MODEL
    root = model_dir()
    if not (_data_path(root) / "config.cfg").is_file():
        download(root)
    return _data_path(root)
