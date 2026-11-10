"""Load ``lepisma.toml`` and merge it over the defaults.

This module stays light (stdlib only) because the commit hook client imports it.
"""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "lepisma.toml"

DEFAULT_HABIT_WORDS: dict[str, str] = {
    # word or phrase -> plainer alternative ("" means just cut it)
    "comprehensive": "full, or cut it",
    "robust": "say what it survives",
    "seamless": "cut it",
    "seamlessly": "cut it",
    "leverage": "use",
    "utilize": "use",
    "delve": "look at",
    "crucial": "say why it matters",
    "streamline": "simplify",
    "ensure": "make sure, or check",
    "facilitate": "help, or let",
    "in order to": "to",
    "it is important to note": "cut it and state the fact",
    # Status-report filler. "successfully" counts only before a verb.
    "successfully": "cut it; say what now works",
    "solid foundation": "say what it lets you build",
}

# Habit words that are fine as the first word of a list item or checklist line.
DEFAULT_OK_AT_ITEM_START = ["ensure"]

DEFAULT_WEAK_VERBS = [
    "be",
    "have",
    "do",
    "make",
    "provide",
    "perform",
    "give",
    "offer",
    "conduct",
    "undertake",
]

# Openers of a paragraph's last sentence that only restate the paragraph.
DEFAULT_SUMMARY_OPENERS = [
    "in summary",
    "in short",
    "in conclusion",
    "to summarize",
    "to sum up",
    "overall",
    "ultimately",
    "all in all",
    "this ensures",
    "this allows",
    "this enables",
    "this means",
    "this makes",
    "this way",
    "together, these",
]

DEFAULT_NOMINAL_SUFFIXES = ["tion", "sion", "ment", "ance", "ence", "ity"]

# Words with a nominal suffix that read as concrete things, not hidden verbs.
DEFAULT_NOMINAL_STOPLIST = [
    # -tion / -sion
    "action", "caption", "collection", "condition", "connection", "edition",
    "exception", "fiction", "function", "junction", "mention", "motion", "nation",
    "notion", "option", "partition", "permission", "portion", "position",
    "question", "ration", "section", "session", "station", "transaction",
    "version", "dimension", "extension", "mission", "television", "division",
    # -ment
    "apartment", "argument", "attachment", "cement", "comment", "department",
    "document", "element", "environment", "equipment", "fragment", "garment",
    "increment", "instrument", "moment", "pigment", "segment", "statement",
    "supplement",
    # -ance / -ence
    "audience", "balance", "conference", "distance", "entrance", "fence",
    "instance", "licence", "science", "sentence", "sequence", "silence",
    # -ity
    "city", "community", "entity", "identity", "quantity", "utility",
]  # fmt: skip


def _str_list(raw: object, key: str) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        msg = f"{key} must be a list of strings"
        raise ConfigError(msg)
    return list(raw)


class ConfigError(ValueError):
    """Raised for an invalid ``lepisma.toml``."""


@dataclass(slots=True)
class LongSentence:
    """R1 settings."""

    enabled: bool = True
    max_words: int = 25
    strong_words: int = 35


@dataclass(slots=True)
class NounStack:
    """R2 settings."""

    enabled: bool = True
    # 3 flagged plain technical terms ("Unix domain socket") in real docs.
    min_nouns: int = 4
    strong_nouns: int = 5
    # A run of only proper nouns is usually a product name ("GitHub Actions CI").
    ignore_all_propn: bool = True
    # More proper nouns than this make a run a name plus a noun ("Claude Code
    # conversation logs", "Google Cloud Platform account"), not a stack.
    max_proper_nouns: int = 1


@dataclass(slots=True)
class HabitWords:
    """R3 settings."""

    enabled: bool = True
    words: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HABIT_WORDS))
    ok_at_item_start: list[str] = field(
        default_factory=lambda: list(DEFAULT_OK_AT_ITEM_START)
    )
    max_per_paragraph: int = 2


@dataclass(slots=True)
class Nominalization:
    """R4 settings."""

    enabled: bool = True
    weak_verbs: list[str] = field(default_factory=lambda: list(DEFAULT_WEAK_VERBS))
    suffixes: list[str] = field(default_factory=lambda: list(DEFAULT_NOMINAL_SUFFIXES))
    stoplist: list[str] = field(default_factory=lambda: list(DEFAULT_NOMINAL_STOPLIST))
    min_length: int = 7
    # Warn when one sentence holds this many abstract nouns, verb or not.
    max_per_sentence: int = 4


@dataclass(slots=True)
class LateVerb:
    """R5 settings."""

    enabled: bool = True
    # Words before the main verb (or its first auxiliary).
    max_words_before: int = 14
    strong_words_before: int = 20


@dataclass(slots=True)
class VagueThis:
    """R6 settings."""

    enabled: bool = True
    # Demonstratives that warn when they stand alone as a sentence's subject.
    words: list[str] = field(default_factory=lambda: ["this", "these"])


@dataclass(slots=True)
class TidySummary:
    """R7 settings."""

    enabled: bool = True
    openers: list[str] = field(default_factory=lambda: list(DEFAULT_SUMMARY_OPENERS))


@dataclass(slots=True)
class Server:
    """Local spaCy server settings."""

    port: int = 8737
    timeout_ms: int = 300


@dataclass(slots=True)
class Config:
    """Full linter configuration."""

    ignore: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=lambda: [".md", ".markdown"])
    long_sentence: LongSentence = field(default_factory=LongSentence)
    noun_stack: NounStack = field(default_factory=NounStack)
    habit_words: HabitWords = field(default_factory=HabitWords)
    nominalization: Nominalization = field(default_factory=Nominalization)
    late_verb: LateVerb = field(default_factory=LateVerb)
    vague_this: VagueThis = field(default_factory=VagueThis)
    tidy_summary: TidySummary = field(default_factory=TidySummary)
    server: Server = field(default_factory=Server)

    def is_ignored(self, path: str) -> bool:
        """Return True when ``path`` matches an ``ignore`` glob or a wrong suffix."""
        posix = Path(path).as_posix()
        if Path(posix).suffix.lower() not in self.extensions:
            return True
        return any(fnmatch.fnmatch(posix, pattern) for pattern in self.ignore)


# rule id -> (name, attribute on Config)
RULES: dict[str, tuple[str, str]] = {
    "R1": ("long-sentence", "long_sentence"),
    "R2": ("noun-stack", "noun_stack"),
    "R3": ("habit-word", "habit_words"),
    "R4": ("nominalization", "nominalization"),
    "R5": ("late-verb", "late_verb"),
    "R6": ("vague-this", "vague_this"),
    "R7": ("tidy-summary", "tidy_summary"),
}


def rule_id(name_or_id: str) -> str | None:
    """Resolve ``R2`` or ``noun-stack`` to ``R2``; None when unknown."""
    key = name_or_id.strip()
    if key.upper() in RULES:
        return key.upper()
    for rid, (name, _) in RULES.items():
        if key.lower() == name:
            return rid
    return None


def _apply(target: object, values: dict[str, Any], section: str) -> None:
    for key, value in values.items():
        attr = key.replace("-", "_")
        if not hasattr(target, attr):
            msg = f"unknown setting [{section}] {key}"
            raise ConfigError(msg)
        current = getattr(target, attr)
        if isinstance(current, bool) != isinstance(value, bool) or not isinstance(
            value, type(current)
        ):
            msg = f"[{section}] {key} must be {type(current).__name__}"
            raise ConfigError(msg)
        setattr(target, attr, value)


def _apply_habit_words(cfg: HabitWords, values: dict[str, Any]) -> None:
    values = dict(values)
    if "words" in values:
        cfg.words = {w.lower(): "" for w in _str_list(values.pop("words"), "words")}
    if "extra_words" in values:
        for w in _str_list(values.pop("extra_words"), "extra_words"):
            cfg.words.setdefault(w.lower(), "")
    if "suggestions" in values:
        sugg = values.pop("suggestions")
        if not isinstance(sugg, dict):
            msg = "[rules.habit-word] suggestions must be a table"
            raise ConfigError(msg)
        cfg.words.update({str(k).lower(): str(v) for k, v in sugg.items()})
    _apply(cfg, values, "rules.habit-word")


def from_dict(data: dict[str, Any]) -> Config:
    """Build a Config from a parsed TOML dict, validating every key."""
    cfg = Config()
    data = dict(data)
    if "ignore" in data:
        cfg.ignore = _str_list(data.pop("ignore"), "ignore")
    if "extensions" in data:
        cfg.extensions = [
            e.lower() for e in _str_list(data.pop("extensions"), "extensions")
        ]
    _apply(cfg.server, data.pop("server", {}), "server")
    for key, values in data.pop("rules", {}).items():
        rid = rule_id(key)
        if rid is None:
            msg = f"unknown rule [rules.{key}]"
            raise ConfigError(msg)
        attr = RULES[rid][1]
        if attr == "habit_words":
            _apply_habit_words(cfg.habit_words, values)
            continue
        target = getattr(cfg, attr)
        settings = dict(values)
        if attr == "nominalization" and "extra_stoplist" in settings:
            extra = _str_list(settings.pop("extra_stoplist"), "extra_stoplist")
            target.stoplist.extend(w.lower() for w in extra)
        _apply(target, settings, f"rules.{key}")
    if data:
        msg = f"unknown top-level setting(s): {', '.join(sorted(data))}"
        raise ConfigError(msg)
    return cfg


def find_config(start: Path) -> Path | None:
    """Walk up from ``start`` and return the first ``lepisma.toml``."""
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load_raw(start: Path) -> dict[str, Any]:
    """Return the parsed TOML for the nearest config, or ``{}`` when none exists."""
    path = find_config(start)
    if path is None:
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)
