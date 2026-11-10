# prose-lint

Soft prose warnings for Markdown written by Claude. This is the spaCy prototype. See
README.md for the design, rules and roadmap.

## Layout

- `markdown.py` turns Markdown into prose blocks and maps each character back to its
  line and column. It drops code, tables, front matter and HTML. Inline code becomes
  the `CODE` placeholder.
- `rules.py` holds R1 to R4. Each is `(block, doc, cfg) -> Iterator[Finding]`.
- `engine.py` runs spaCy and the rules. Only it and `server.py` import spaCy.
- `client.py` is the commit hook client. **Stdlib only**; it never raises and always
  exits 0. Keep spaCy and FastAPI out of it, and out of `config.py`, `models.py` and
  `report.py`, which it imports.
- `server.py` is the FastAPI server on 127.0.0.1:8737, with an LRU cache and idle exit.
- `corpus/` is the baseline test set. `tests/test_corpus.py` checks that bad docs score
  far worse than good ones.

## Tuning a rule

Run `uv run prose-lint stats corpus/bad corpus/good` before and after a change to a
rule or threshold. A good change keeps bad docs high and good docs low. Add a test to
`tests/test_rules.py` for each false positive you fix.

## Commands

- `uv run poe check` — run lint (incl. ruff `S` security rules), typecheck, vulns, test-lint, clones, then tests
- `uv run poe fix` — auto-format and fix lint issues
- `uv run poe test` — run tests only
- `uv run poe check-all` — run all checks including dead-code and unused-deps

## Stack

uv, ruff (lint/format), ty (type check), pytest, poethepoet (task runner)

## Toolbox

The [aesop toolbox](https://mojzis.github.io/aesop/llms.txt) is wired in here. Every
tool explains itself — run `uv run <tool> guide` before reaching for flags, and
`uv run <tool> guide tune` before changing a threshold. Call them as `uv run <tool>`;
ty-find's binary is `tyf`.

### On every commit

`prose-lint hook` runs first in `hooks/pre-commit`: it lints staged Markdown, warns only and never blocks.
**madoqua** is the Python commit hook (`hooks/pre-commit`, `core.hooksPath=hooks`). It
acts on staged `.py`/`.pyi` files only — a commit without one is a silent no-op, not a
verified hook.

| phase | steps |
| --- | --- |
| fix (rewrites and re-stages) | `ruff check --fix`, `ruff format` |
| check (blocks) | `ruff check`, `ty check`, `biston scan --focus-args`, `zorilla check`, `gerenuk run` |

Whole hook runs in ~0.3 s on this repo (gerenuk ~0.27 s of that; `uv run madoqua stats`
for current numbers). Don't commit with `--no-verify` or `MADOQUA_SKIP` to get past a
check that is telling the truth.

Two changes from the hook this replaced:

- `ty check` was repo-wide, it is now **staged-only**. Repo-wide diagnostics no longer
  block a clean commit, but a file with existing diagnostics blocks the first commit
  that touches it. `uv run poe typecheck` still checks everything.
- **bandit is gone.** Security checks are ruff's flake8-bandit `S` rules, so they now run
  on commit via `ruff check`; `tests/**` ignores S101/S105/S106 in `per-file-ignores`.

### Every now and then

- `uv run pycoati . --format pretty` — scores every test for suspicion and prints a
  remediation ladder. Run it before a test-cleanup session. Never put it in a hook or
  CI: it runs the suite three times. It needs pytest-cov or coverage is silently null.

### On demand — instead of grep

- `uv run tyf find <symbol>` / `tyf refs` / `tyf list <file>` / `tyf calls` — type-aware
  symbol lookup. **Use these instead of grep** for definitions and references; grep
  cannot tell a definition from a string that happens to match.
- `uv run gerenuk audit <file>` — lists symbols in a module that nothing references.
- `uv run gerenuk impacted-tests` — which tests a working-tree diff reaches, and why.

### Fresh clone

```
uv sync
git config core.hooksPath hooks   # once; local config, not tracked
```

Don't run `madoqua install`: it overwrites `hooks/pre-commit` and drops the
prose-lint line.

### Refreshing the toolbox

```
uv lock --refresh --upgrade-package madoqua --upgrade-package gerenuk --upgrade-package biston --upgrade-package zorilla --upgrade-package pycoati --upgrade-package ty-find && uv sync
```

`--refresh` matters: without it uv may serve a cached index and miss a release
published minutes ago.

## Notes

- ty is in beta — may produce false positives. Prefer `# ty: ignore[rule]` over blanket suppression.
- The commit hook auto-fixes and restages files. Only blocks on unfixable issues.
- gerenuk diffs the **working tree** against `origin/main`, so unstaged edits count, and
  any commit touching `pyproject.toml` or `uv.lock` runs the full suite. `--base HEAD`
  scopes it to the commit itself.
- ty-find's index goes stale after the hook's `ruff format` rewrites a file. The tell is
  `tyf refs <sym>` listing only the definition, or gerenuk reporting `selected` with an
  empty list. `uv run tyf daemon restart` fixes it.
