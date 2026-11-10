"""Output formatting: text lines, JSON, and density stats."""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import TextIO

from prose_lint.config import RULES
from prose_lint.models import FileResult

NAME_W = 44  # width of the file column in stats output


def per_1000(count: int, words: int) -> float:
    """Warnings per 1,000 words."""
    return count * 1000 / words if words else 0.0


def print_results(
    results: list[FileResult],
    fmt: str,
    *,
    footer: bool = False,
    out: TextIO | None = None,
) -> None:
    """Print warnings as ``file:line:col rule-id message`` lines or as JSON."""
    out = out or sys.stdout
    warnings = [w for r in results for w in r.warnings]
    if fmt == "json":
        words = sum(r.words for r in results)
        json.dump(
            {
                "warnings": [w.to_dict() for w in warnings],
                "summary": {
                    "files": len(results),
                    "words": words,
                    "warnings": len(warnings),
                    "per_1000_words": round(per_1000(len(warnings), words), 1),
                },
            },
            out,
            indent=2,
        )
        out.write("\n")
        return
    for w in warnings:
        out.write(w.to_text() + "\n")
    if footer and warnings:
        files = len({w.path for w in warnings})
        out.write(
            f"prose-lint: {len(warnings)} warning(s) in {files} file(s); "
            "warn-only, the commit goes ahead. Rewrite the flagged prose, or add "
            "<!-- prose-lint: disable R<n> --> where a rule is wrong.\n"
        )


def print_stats(groups: dict[str, list[FileResult]], out: TextIO | None = None) -> None:
    """Print warnings per 1,000 words per file and per group, broken down by rule."""
    out = out or sys.stdout
    rule_ids = list(RULES)
    header = f"{'file':{NAME_W}} {'words':>6} {'per1k':>6} " + " ".join(
        f"{r:>5}" for r in rule_ids
    )
    for group, results in groups.items():
        out.write(f"\n== {group}\n{header}\n")
        total: Counter[str] = Counter()
        words = 0
        for r in results:
            counts = Counter(w.rule for w in r.warnings)
            total.update(counts)
            words += r.words
            cells = " ".join(f"{per_1000(counts[x], r.words):5.1f}" for x in rule_ids)
            name = r.path if len(r.path) <= NAME_W else "…" + r.path[-(NAME_W - 1) :]
            dens = per_1000(len(r.warnings), r.words)
            out.write(f"{name:{NAME_W}} {r.words:6} {dens:6.1f} {cells}\n")
        cells = " ".join(f"{per_1000(total[x], words):5.1f}" for x in rule_ids)
        dens = per_1000(sum(total.values()), words)
        out.write(f"{'TOTAL':{NAME_W}} {words:6} {dens:6.1f} {cells}\n")
