"""Turn Markdown into plain prose blocks that keep a map back to source positions.

Code blocks, tables, front matter, HTML and link targets are dropped. Inline code
and bare URLs become a placeholder word so sentences still parse, and rules can
tell the placeholder apart from real words via ``Block.code_spans``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from prose_lint.config import RULES, rule_id

BlockKind = Literal["paragraph", "list", "heading", "quote"]

PLACEHOLDER = "CODE"
ALL_RULES = frozenset(RULES)

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])(\s+)(\[[ xX]\]\s+)?")
_QUOTE = re.compile(r"^\s{0,3}>\s?")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
_LINK_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S")
_HTML_BLOCK = re.compile(r"^\s{0,3}</?[A-Za-z][\w-]*[\s/>]|^\s{0,3}<!--")
_DIRECTIVE = re.compile(
    r"<!--\s*prose-lint:\s*(disable-next|disable|enable)\b([^>]*?)-->", re.IGNORECASE
)
_IDENTIFIER_ITEM = re.compile(r"^[\w.\-/:`=\[\]()]+,?$")

_INLINE = re.compile(
    r"(?P<code>(?P<ticks>`+).+?(?P=ticks))"
    r"|(?P<image>!\[[^\]]*\]\([^)]*\))"
    r"|(?P<link>\[(?P<ltext>[^\]]*)\](?:\([^)]*\)|\[[^\]]*\]))"
    r"|(?P<auto><(?:https?|mailto):[^>]+>)"
    r"|(?P<url>https?://[^\s)>\]]+)"
    r"|(?P<html><!--.*?-->|</?[A-Za-z][^>]*>)"
    r"|(?P<escape>\\[\\`*_{}\[\]()#+\-.!|>~])"
    r"|(?P<emph>\*+|~~|(?<!\w)_+|_+(?!\w))"
)


@dataclass(slots=True)
class Block:
    """One paragraph, list item, heading or quote as plain text."""

    kind: BlockKind
    text: str = ""
    level: int = 0  # heading level 1-6; 0 for other blocks
    # origins[i] is the (line, col) in the source of text[i]; both 1-based.
    origins: list[tuple[int, int]] = field(default_factory=list)
    code_spans: list[tuple[int, int]] = field(default_factory=list)
    disabled: frozenset[str] = frozenset()
    raw: list[str] = field(default_factory=list)

    def position(self, offset: int) -> tuple[int, int]:
        """Source (line, col) of the character at ``offset``."""
        if not self.origins:
            return (1, 1)
        return self.origins[min(max(offset, 0), len(self.origins) - 1)]

    def in_code(self, start: int, end: int) -> bool:
        """True when the range overlaps a code placeholder."""
        return any(s < end and start < e for s, e in self.code_spans)

    def _add(self, chunk: str, line: int, col: int, *, code: bool = False) -> None:
        start = len(self.text)
        self.text += chunk
        self.origins.extend((line, col) for _ in chunk)
        if code:
            self.code_spans.append((start, len(self.text)))

    def add_line(self, content: str, line: int, col0: int) -> None:
        """Append one source line; ``col0`` is the 0-based column of ``content``."""
        self.raw.append(content)
        if self.text:
            last = self.origins[-1]
            self.text += " "
            self.origins.append(last)
        pos = 0
        for m in _INLINE.finditer(content):
            for i in range(pos, m.start()):
                self._add(content[i], line, col0 + i + 1)
            col = col0 + m.start() + 1
            kind = m.lastgroup
            if kind in {"code", "auto", "url"}:
                self._add(PLACEHOLDER, line, col, code=True)
            elif kind == "link":
                text_col = col + 1
                ltext = m.group("ltext")
                for i, ch in enumerate(ltext):
                    self._add(ch, line, text_col + i)
            elif kind == "escape":
                self._add(m.group()[1], line, col + 1)
            # image, html, emph: dropped
            pos = m.end()
        for i in range(pos, len(content)):
            self._add(content[i], line, col0 + i + 1)

    def is_identifier_list_item(self) -> bool:
        """True for list items like ``- `max_retries` `` or ``- user_id``."""
        if self.kind != "list":
            return False
        stripped = self.text.strip()
        if not stripped:
            return True
        parts = stripped.split()
        if len(parts) == 1:
            return bool(_IDENTIFIER_ITEM.match(parts[0]))
        return all(p.strip(",.;:") == PLACEHOLDER for p in parts)


class _Disabler:
    """Tracks ``<!-- prose-lint: ... -->`` directives while scanning."""

    def __init__(self) -> None:
        self.active: set[str] = set()
        self.next_only: set[str] = set()

    @staticmethod
    def _rules(arg: str) -> set[str]:
        names = [n for n in re.split(r"[\s,]+", arg.strip()) if n]
        if not names:
            return set(ALL_RULES)
        return {rid for n in names if (rid := rule_id(n))}

    def feed(self, line: str) -> bool:
        """Apply any directive on ``line``; True if the line held one."""
        found = False
        for m in _DIRECTIVE.finditer(line):
            found = True
            action, rules = m.group(1).lower(), self._rules(m.group(2))
            if action == "disable":
                self.active |= rules
            elif action == "enable":
                self.active -= rules
            else:
                self.next_only |= rules
        return found

    def take(self) -> frozenset[str]:
        """Rules disabled for the block that starts now; consumes disable-next."""
        result = frozenset(self.active | self.next_only)
        self.next_only = set()
        return result


def _skip_front_matter(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].strip() in {"---", "..."}:
            return i + 1
    return 0


def _is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def parse(source: str) -> list[Block]:  # noqa: PLR0912, PLR0915 - one scanner loop
    """Split Markdown ``source`` into prose blocks."""
    lines = source.splitlines()
    blocks: list[Block] = []
    disabler = _Disabler()
    current: Block | None = None
    fence: str | None = None
    in_html_comment = False
    in_table = False

    def close() -> None:
        nonlocal current
        if current is not None and current.text.strip():
            blocks.append(current)
        current = None

    def start(kind: BlockKind) -> Block:
        close()
        return Block(kind=kind, disabled=disabler.take())

    i = _skip_front_matter(lines)
    while i < len(lines):
        line = lines[i]
        lineno = i + 1
        i += 1

        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence[0] * len(fence)) and not stripped.strip(
                fence[0]
            ):
                fence = None
            continue
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue

        if disabler.feed(line) and not _DIRECTIVE.sub("", line).strip():
            close()
            continue

        if not line.strip():
            close()
            in_table = False
            continue

        if m := _FENCE.match(line):
            close()
            fence = m.group(1)
            continue

        if in_table and "|" in line:
            continue
        in_table = False

        if _TABLE_SEP.match(line) and (current is not None or _is_table_row(line)):
            # The previous line was the table header, not prose.
            if current is not None and current.raw:
                current = None
            in_table = True
            continue
        if _is_table_row(line):
            close()
            in_table = True
            continue

        if line.lstrip().startswith("<!--") and "-->" not in line:
            close()
            in_html_comment = True
            continue
        if _HTML_BLOCK.match(line) or _LINK_DEF.match(line):
            close()
            continue

        if (
            current is not None
            and current.kind == "paragraph"
            and _SETEXT.match(line)
            and len(current.raw) == 1
        ):
            current.kind = "heading"
            current.level = 1 if line.strip().startswith("=") else 2
            close()
            continue
        if _HR.match(line):
            close()
            continue

        if m := _HEADING.match(line):
            current = blk = start("heading")
            blk.level = len(m.group(1))
            blk.add_line(m.group(2), lineno, m.start(2))
            close()
            continue

        if m := _LIST.match(line):
            current = blk = start("list")
            blk.add_line(line[m.end() :], lineno, m.end())
            continue

        if m := _QUOTE.match(line):
            blk = current
            if blk is None or blk.kind != "quote":
                current = blk = start("quote")
            blk.add_line(line[m.end() :], lineno, m.end())
            continue

        indent = len(line) - len(line.lstrip())
        if current is None and indent >= 4:  # noqa: PLR2004 - CommonMark code indent
            # Indented code block (only when it does not continue a block).
            continue

        blk = current
        if blk is None:
            current = blk = start("paragraph")
        blk.add_line(line.strip(), lineno, indent)

    close()
    return blocks
