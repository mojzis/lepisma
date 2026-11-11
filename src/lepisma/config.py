"""Load ``lepisma.toml`` and merge it over the defaults.

This module stays light (stdlib only) because the commit hook client imports it.
"""

from __future__ import annotations

import fnmatch
import sys
import tomllib
from collections.abc import Iterable, Sequence
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


# Acronyms a technical reader knows. Capitals whose lowercase form is a common
# word, such as "PATH" and "NOT", need no entry here.
DEFAULT_KNOWN_ACRONYMS = [
    "AI", "API", "ASCII", "CD", "CI", "CLI", "CPU", "CSS", "CSV", "DNS", "EOF",
    "EU", "FAQ", "GB", "GPU", "HTML", "HTTP", "HTTPS", "ID", "IDE", "IP", "JSON",
    "KB", "LIX", "MB", "MIT", "OK", "OS", "PDF", "PID", "PR", "RAM", "README",
    "REST", "SDK", "SMS", "SQL", "SSH", "TB", "TCP", "TODO", "TOML", "TTY", "UI",
    "UK", "URI", "URL", "US", "UTC", "UTF", "UUID", "XML", "YAML",
]  # fmt: skip


# Words that claim sincerity or precision in place of showing it.
DEFAULT_SINCERITY = ["genuinely", "exactly", "deliberately", "quietly", "silently"]

# Figures of speech that stand in for a plain name. Inflections match too.
DEFAULT_FIGURATIVE = [
    "seam", "verdict", "load-bearing", "shape", "rung", "floor", "land", "surface",
    "wire", "drift",
]  # fmt: skip


class ConfigError(ValueError):
    """Raised for an invalid ``lepisma.toml`` or glossary."""


# term -> its fields; both fields are optional, but an entry needs one.
Glossary = dict[str, dict[str, str]]
GLOSSARY_FIELDS = ("expansion", "definition")


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
class InterruptionLoad:
    """R8 settings."""

    enabled: bool = True
    # Dashes, parentheses, semicolons and mid-sentence colons in one sentence.
    warn_at: int = 2
    strong_at: int = 3
    # A dash or colon after this few words separates a label ("`name` - text").
    label_words: int = 4
    # A parenthesis with fewer words is a gloss ("`-d` (docs)"), not an aside.
    min_paren_words: int = 3


@dataclass(slots=True)
class ContrastFrame:
    """R9 settings."""

    enabled: bool = True
    # A document with fewer frames than this is never flagged.
    min_count: int = 3
    # Frames per 1,000 words a document may hold; strong at twice this.
    max_per_1000: float = 4.0


@dataclass(slots=True)
class UndefinedTerm:
    """R10 settings."""

    enabled: bool = True
    # Acronyms that need no expansion; `extra_known` in the config adds to it.
    known_acronyms: list[str] = field(
        default_factory=lambda: list(DEFAULT_KNOWN_ACRONYMS)
    )
    # Also flag rare words that a document uses often and never defines.
    # Off by default: most hits in real docs are jargon the reader knows.
    rare_terms: bool = False
    # A rare word must appear this often in one document to count as a term.
    min_uses: int = 3
    # Rare words that need no definition in this repo (tool names, jargon).
    known_terms: list[str] = field(default_factory=list)
    # Merged glossary entries: term -> {"expansion": ..., "definition": ...}.
    # `load_raw` builds it from the glossary files; `from_dict` takes it inline.
    glossary: Glossary = field(default_factory=dict)
    # Globs for files read without the glossary at hand, such as README.md.
    # The glossary is not applied to them, so they must spell terms out.
    spell_out_in: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Emphasis:
    """R11 settings."""

    enabled: bool = True
    sincerity: list[str] = field(default_factory=lambda: list(DEFAULT_SINCERITY))
    figurative: list[str] = field(default_factory=lambda: list(DEFAULT_FIGURATIVE))
    # Per family: fewer hits than this never warn.
    min_count: int = 3
    # Per family: hits per 1,000 words a document may hold; strong at twice this.
    max_per_1000: float = 3.0


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
    interruption_load: InterruptionLoad = field(default_factory=InterruptionLoad)
    contrast_frame: ContrastFrame = field(default_factory=ContrastFrame)
    undefined_term: UndefinedTerm = field(default_factory=UndefinedTerm)
    emphasis: Emphasis = field(default_factory=Emphasis)
    server: Server = field(default_factory=Server)

    def is_ignored(self, path: str) -> bool:
        """Return True when ``path`` matches an ``ignore`` glob or a wrong suffix."""
        if Path(path).suffix.lower() not in self.extensions:
            return True
        return _matches(path, self.ignore)

    def spells_out(self, path: str) -> bool:
        """Return True when ``path`` matches a ``spell_out_in`` glob of R10."""
        return _matches(path, self.undefined_term.spell_out_in)


def _matches(path: str, globs: list[str]) -> bool:
    posix = Path(path).as_posix()
    return any(fnmatch.fnmatch(posix, pattern) for pattern in globs)


# rule id -> (name, attribute on Config)
RULES: dict[str, tuple[str, str]] = {
    "R1": ("long-sentence", "long_sentence"),
    "R2": ("noun-stack", "noun_stack"),
    "R3": ("habit-word", "habit_words"),
    "R4": ("nominalization", "nominalization"),
    "R5": ("late-verb", "late_verb"),
    "R6": ("vague-this", "vague_this"),
    "R7": ("tidy-summary", "tidy_summary"),
    "R8": ("interruption-load", "interruption_load"),
    "R9": ("contrast-frame", "contrast_frame"),
    "R10": ("undefined-term", "undefined_term"),
    "R11": ("emphasis", "emphasis"),
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
    for key, given in values.items():
        value = given
        attr = key.replace("-", "_")
        if not hasattr(target, attr):
            msg = f"unknown setting [{section}] {key}"
            raise ConfigError(msg)
        current = getattr(target, attr)
        if isinstance(current, float) and type(value) is int:
            value = float(value)
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
        if attr == "undefined_term" and "extra_known" in settings:
            extra = _str_list(settings.pop("extra_known"), "extra_known")
            target.known_acronyms.extend(w.upper() for w in extra)
        if attr == "undefined_term" and "glossary" in settings:
            target.glossary = glossary_entries(
                settings.pop("glossary"), f"[rules.{key}] glossary"
            )
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


def _warn(msg: str) -> None:
    print(f"lepisma: {msg}", file=sys.stderr)  # noqa: T201


def glossary_entries(raw: object, source: str) -> Glossary:
    """Validate glossary entries: one table per term, with string fields."""
    if not isinstance(raw, dict):
        msg = f"{source}: must be a table of entries (load_raw reads the file list)"
        raise ConfigError(msg)
    entries: Glossary = {}
    for name, entry in raw.items():
        where = f"{source}: [{name}]"
        if not isinstance(entry, dict):
            msg = f"{where} must be a table"
            raise ConfigError(msg)
        unknown = sorted(set(entry) - set(GLOSSARY_FIELDS))
        if unknown:
            msg = f"{where} has unknown field(s): {', '.join(unknown)}"
            raise ConfigError(msg)
        if not entry:
            msg = f"{where} needs an expansion or a definition"
            raise ConfigError(msg)
        for key, value in entry.items():
            if not isinstance(value, str):
                msg = f"{where} {key} must be a string"
                raise ConfigError(msg)
        entries[str(name)] = dict(entry)
    return entries


def read_glossary(path: Path) -> Glossary:
    """Parse and validate one glossary file."""
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except OSError as exc:
        msg = f"{path}: cannot read glossary ({exc.strerror or exc})"
        raise ConfigError(msg) from exc
    except ValueError as exc:  # TOMLDecodeError, or bytes that are not UTF-8
        msg = f"{path}: invalid TOML ({exc})"
        raise ConfigError(msg) from exc
    return glossary_entries(raw, str(path))


def merge_glossaries(layers: Iterable[tuple[str, Glossary]]) -> Glossary:
    """Layer glossaries in order. A later entry's fields win; each expansion
    that changes is reported on stderr."""
    merged: Glossary = {}
    origin: dict[str, str] = {}
    for source, entries in layers:
        for name, entry in entries.items():
            old = merged.get(name, {})
            was, now = old.get("expansion"), entry.get("expansion")
            if was is not None and now is not None and was != now:
                _warn(
                    f'glossary conflict for "{name}": "{now}" from {source} '
                    f'replaces "{was}" from {origin[name]}'
                )
            if now is not None:
                origin[name] = source
            merged[name] = {**old, **entry}
    return merged


def _inline_glossaries(
    raw: dict[str, Any], base: Path, extra: Sequence[str | Path]
) -> dict[str, Any]:
    """Replace R10's ``glossary`` file list by the merged entries.

    Paths in the config are relative to ``base``, the config's directory;
    ``extra`` paths (the ``--glossary`` flag) are relative to the current
    directory and come last. A bad file is reported on stderr and left out.
    """
    rules = raw.get("rules", {})
    if not isinstance(rules, dict):
        return raw  # from_dict reports it
    layers: list[tuple[str, Glossary]] = []
    files: list[Path] = []
    target: dict[str, Any] | None = None
    for key, section in rules.items():
        if rule_id(key) != "R10" or not isinstance(section, dict):
            continue
        if "glossary" not in section:
            continue
        target = section
        given = section.pop("glossary")
        if isinstance(given, dict):  # entries written straight into the config
            layers.append((CONFIG_NAME, glossary_entries(given, CONFIG_NAME)))
        else:
            name = f"[rules.{key}] glossary"
            files.extend(base / p for p in _str_list(given, name))
    files.extend(Path(p) for p in extra)
    if target is None and not files:
        return raw
    for path in files:
        try:
            layers.append((str(path), read_glossary(path)))
        except ConfigError as exc:
            _warn(f"glossary skipped: {exc}")
    if target is None:
        target = raw.setdefault("rules", {}).setdefault(RULES["R10"][0], {})
    target["glossary"] = merge_glossaries(layers)
    return raw


def load_raw(start: Path, glossaries: Sequence[str | Path] = ()) -> dict[str, Any]:
    """Return the parsed TOML for the nearest config, or ``{}`` when none exists.

    Glossary files named by the config and then by ``glossaries`` are read here
    and inlined, so the result is all a server needs to lint.
    """
    path = find_config(start)
    raw: dict[str, Any] = {}
    if path is not None:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    return _inline_glossaries(raw, path.parent if path else start, glossaries)
