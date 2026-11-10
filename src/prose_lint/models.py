"""Data types shared by the engine, server and client."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["warning", "strong"]


@dataclass(frozen=True, slots=True)
class Finding:
    """A rule hit inside one block, before it is mapped back to the source file."""

    rule: str
    offset: int
    message: str
    severity: Severity = "warning"


@dataclass(frozen=True, slots=True)
class Warning:
    """A rule hit with its position in the source file."""

    path: str
    line: int
    col: int
    rule: str
    name: str
    severity: Severity
    message: str

    def to_text(self) -> str:
        """Format as ``file:line:col rule-id message``."""
        return f"{self.path}:{self.line}:{self.col} {self.rule} {self.message}"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Warning:
        """Build from the dict produced by :meth:`to_dict`."""
        return cls(**data)


@dataclass(frozen=True, slots=True)
class FileResult:
    """All warnings for one file, plus its prose word count for density stats."""

    path: str
    words: int
    warnings: tuple[Warning, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dict."""
        return {
            "path": self.path,
            "words": self.words,
            "warnings": [w.to_dict() for w in self.warnings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileResult:
        """Build from the dict produced by :meth:`to_dict`."""
        return cls(
            path=str(data["path"]),
            words=int(data["words"]),
            warnings=tuple(Warning.from_dict(w) for w in data["warnings"]),
        )
