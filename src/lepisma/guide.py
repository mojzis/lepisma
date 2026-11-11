"""``lepisma guide``: one Markdown page of instructions for an agent.

Pages live in ``lepisma/guide/*.md``. ``{{section.key}}`` placeholders are filled
from the ``Config`` defaults, so thresholds in the pages follow the code. Stdlib only.
"""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

from lepisma.config import CONFIG_NAME, Config, find_config

TOPICS: dict[str, str] = {
    "setup": "not wired in yet: install, config, hook, first run",
    "triage": "lepisma printed warnings: what they mean, how to fix them",
    "tune": "reference: config keys, defaults, exit codes, changing a threshold",
}

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\.([a-z_0-9]+)\s*\}\}")


def _default(match: re.Match[str]) -> str:
    value = getattr(getattr(Config(), match[1]), match[2])
    return str(value).lower() if isinstance(value, bool) else str(value)


def render(topic: str) -> str:
    """The page for ``topic`` with defaults filled in."""
    text = files("lepisma").joinpath("guide", f"{topic}.md").read_text("utf-8")
    return _PLACEHOLDER.sub(_default, text)


def detect(cwd: Path) -> tuple[str, str]:
    """Pick a topic from files only: ``(topic, reason)``."""
    config = find_config(cwd)
    if config is not None:
        return "triage", f"configured via {config}"
    pyproject = cwd / "pyproject.toml"
    if pyproject.is_file() and "lepisma hook" in pyproject.read_text("utf-8"):
        return "triage", "configured via pyproject.toml madoqua step"
    return "setup", f"no {CONFIG_NAME} here or above, no hook step in pyproject.toml"
