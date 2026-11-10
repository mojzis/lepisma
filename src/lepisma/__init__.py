"""Soft prose warnings for Markdown docs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lepisma")
except PackageNotFoundError:  # pragma: no cover - running from a bare checkout
    __version__ = "0.0.0"


def build_id() -> str:
    """Version plus a hash of this package's source.

    The hook restarts a server whose build id differs from its own, so code
    changes take effect without a version bump.
    """
    import hashlib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.read_bytes())
    return f"{__version__}+{digest.hexdigest()[:12]}"
