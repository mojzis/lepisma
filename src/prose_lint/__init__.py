"""Soft prose warnings for Markdown docs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("prose-lint")
except PackageNotFoundError:  # pragma: no cover - running from a bare checkout
    __version__ = "0.0.0"
