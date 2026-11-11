"""Command line entry point. Heavy modules are imported inside each command."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from lepisma.guide import TOPICS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lepisma.config import Config
    from lepisma.models import FileResult

HOOK_MARKER = "lepisma hook"


def _walk(directory: Path, extensions: list[str]) -> list[Path]:
    """Docs under ``directory``, skipping hidden folders like .git and .venv."""
    return sorted(
        f
        for f in directory.rglob("*")
        if f.is_file()
        and f.suffix.lower() in extensions
        and not any(part.startswith(".") for part in f.relative_to(directory).parts)
    )


def _collect(paths: list[str], cfg: Config, *, use_ignore: bool) -> list[Path]:
    """Files named in ``paths`` plus docs found in named folders. ``ignore`` globs
    only filter files found by walking a folder."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found = _walk(p, cfg.extensions)
            if use_ignore:
                found = [f for f in found if not cfg.is_ignored(str(f))]
            files.extend(found)
        elif p.is_file():
            files.append(p)
        else:
            print(f"lepisma: no such file: {raw}", file=sys.stderr)  # noqa: T201
    return files


def _lint_paths(
    paths: list[str], *, use_ignore: bool = True, glossaries: Sequence[str] = ()
) -> list[FileResult]:
    """Lint files and folders."""
    from lepisma.config import from_dict, load_raw  # noqa: PLC0415
    from lepisma.engine import lint_text  # noqa: PLC0415

    cfg = from_dict(load_raw(Path.cwd(), glossaries))
    files = _collect(paths, cfg, use_ignore=use_ignore)
    return [lint_text(str(f), f.read_text(encoding="utf-8"), cfg) for f in files]


def cmd_check(args: argparse.Namespace) -> int:
    """Lint files in-process (no server). Exit 1 on warnings only with --strict."""
    from lepisma.report import print_results  # noqa: PLC0415

    results = _lint_paths(args.paths, glossaries=args.glossary)
    print_results(results, args.format)
    has_warnings = any(r.warnings for r in results)
    return 1 if args.strict and has_warnings else 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Warnings per 1,000 words, one group per argument. Ignores ``ignore``,
    since stats are mostly run on the test corpus."""
    from lepisma.report import print_stats  # noqa: PLC0415

    print_stats({p: _lint_paths([p], use_ignore=False) for p in args.paths})
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    """Readability stats for whole docs: Parquet tables plus report.md."""
    from lepisma.config import from_dict, load_raw  # noqa: PLC0415

    try:
        from lepisma.measure import Measurer  # noqa: PLC0415
        from lepisma.measure_report import print_summary, render  # noqa: PLC0415
    except ImportError as exc:
        print(  # noqa: T201
            f"lepisma: measure needs the 'measure' extra ({exc.name} missing); "
            'install "lepisma[measure]"',
            file=sys.stderr,
        )
        return 2
    cfg = from_dict(load_raw(Path.cwd()))
    files = _collect(args.paths, cfg, use_ignore=not args.no_ignore)
    if not files:
        print("lepisma: no docs found", file=sys.stderr)  # noqa: T201
        return 1
    result = Measurer(cfg).measure_paths(files)
    out = Path(args.out)
    result.write(out)
    (out / "report.md").write_text(render(result, args.min_words), encoding="utf-8")
    print_summary(result, args.min_words, sys.stdout)
    print(f"wrote {out}/report.md and {out}/*.parquet")  # noqa: T201
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Pre-commit hook: lint staged docs via the server; never fails."""
    from lepisma.client import run_hook  # noqa: PLC0415

    return run_hook(
        args.files, fmt=args.format, wait_s=args.wait, glossaries=args.glossary
    )


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the local spaCy server in the foreground."""
    from lepisma.client import DEFAULT_IDLE_TIMEOUT_S  # noqa: PLC0415
    from lepisma.config import from_dict, load_raw  # noqa: PLC0415
    from lepisma.server import serve  # noqa: PLC0415

    port = args.port or from_dict(load_raw(Path.cwd())).server.port
    idle = DEFAULT_IDLE_TIMEOUT_S if args.idle_timeout is None else args.idle_timeout
    serve(port, idle)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop a running server."""
    from lepisma.client import post  # noqa: PLC0415

    try:
        post(args.port, "/shutdown", {}, 1.0)
    except OSError:
        print("lepisma: no server running", file=sys.stderr)  # noqa: T201
        return 1
    return 0


def hook_command() -> str:
    """Shell command the git hook should run."""
    exe = shutil.which("lepisma")
    if exe:
        return f'"{exe}" hook'
    return f'"{sys.executable}" -m lepisma hook'


def cmd_install_hook(_args: argparse.Namespace) -> int:
    """Add the lepisma line to this repo's pre-commit hook."""
    hooks = Path(
        subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    hook = hooks / "pre-commit"
    line = f"{hook_command()} || true  # {HOOK_MARKER}: warn-only, never blocks\n"
    if hook.exists():
        text = hook.read_text()
        if HOOK_MARKER in text:
            print(f"lepisma: already in {hook}")  # noqa: T201
            return 0
        lines = text.splitlines(keepends=True)
        # Run before the existing hook body, which may end in `exec`.
        at = 1 if lines and lines[0].startswith("#!") else 0
        lines.insert(at, line)
        hook.write_text("".join(lines))
    else:
        hooks.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\n" + line)
    hook.chmod(hook.stat().st_mode | 0o111)
    print(f"lepisma: added to {hook}")  # noqa: T201
    return 0


def cmd_guide(args: argparse.Namespace) -> int:
    """Print the agent guide for a topic, auto-picked when none is given."""
    from lepisma.guide import detect, render  # noqa: PLC0415

    if args.topic:
        topic, head = args.topic, f"# lepisma guide: {args.topic}"
    else:
        topic, reason = detect(Path.cwd())
        head = f"# lepisma guide: {reason} -> {topic}"
    try:
        sys.stdout.write(f"{head}\n\n{render(topic)}")
        sys.stdout.flush()
    except OSError:
        return 1
    return 0


def _add_glossary_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--glossary",
        action="append",
        default=[],
        metavar="PATH",
        help="glossary file for R10, layered after the config's; repeatable",
    )


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for all subcommands."""
    parser = argparse.ArgumentParser(
        prog="lepisma",
        description="Soft warnings for hard-to-read Markdown prose. "
        "Run `lepisma guide` first.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "guide",
        help="instructions for an agent: run this first",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Print Markdown instructions for an agent and exit 0.\n\n"
        "topics:\n"
        + "".join(f"  {name:<8}{line}\n" for name, line in TOPICS.items())
        + "\nWith no topic, pick one from files: triage when lepisma.toml is\n"
        "in the current directory or above, or pyproject.toml here has a\n"
        "`lepisma hook` step; otherwise setup.",
    )
    p.add_argument("topic", nargs="?", choices=list(TOPICS))
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("check", help="lint files or directories in-process")
    p.add_argument("paths", nargs="+")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument(
        "--strict", action="store_true", help="exit 1 when there are warnings"
    )
    _add_glossary_flag(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("stats", help="warnings per 1,000 words; one group per path")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser(
        "measure", help="readability stats for whole docs (needs the measure extra)"
    )
    p.add_argument("paths", nargs="+")
    p.add_argument("--out", default="stats", help="output folder (default: stats)")
    p.add_argument(
        "--min-words",
        type=int,
        default=100,
        help="smallest section or file to rank in the report (default: 100)",
    )
    p.add_argument(
        "--no-ignore", action="store_true", help="also measure files matching ignore"
    )
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("hook", help="pre-commit hook: lint staged docs via the server")
    p.add_argument(
        "files",
        nargs="*",
        help="staged docs to lint (madoqua passes these); default: ask git",
    )
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument(
        "--wait",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="start the server and wait for it instead of skipping",
    )
    _add_glossary_flag(p)
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("serve", help="run the spaCy server in the foreground")
    p.add_argument("--port", type=int, default=None)
    p.add_argument(
        "--idle-timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="exit after this long without requests (0 = never; default 4 h)",
    )
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("stop", help="stop the running server")
    p.add_argument("--port", type=int, default=8737)
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("install-hook", help="add lepisma to .git pre-commit hook")
    p.set_defaults(func=cmd_install_hook)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        from lepisma.spacy_model import ModelError  # noqa: PLC0415

        if not isinstance(exc, ModelError):
            raise
        print(f"lepisma: {exc}", file=sys.stderr)  # noqa: T201
        return 2
