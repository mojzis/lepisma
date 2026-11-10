## Setup: wire prose-lint into this repository

prose-lint gives soft warnings on hard-to-read Markdown. It runs as a warn-only
commit hook and never blocks a commit. Nothing here says it is set up yet: there
is no `prose-lint.toml` and no `prose-lint hook` step in `pyproject.toml`.

### Steps

1. Add it as a dev dependency, so the hook finds it in `.venv`:

   ```
   uv add --dev "prose-lint @ git+https://github.com/mojzis/prose-linter"
   ```

2. Create `prose-lint.toml` at the repo root. An empty file is valid; every key
   has a default. Add an `ignore` list for generated or vendored docs:

   ```toml
   ignore = ["CHANGELOG.md", "vendor/**"]
   ```

3. Hook it into commits. With madoqua (a `[tool.madoqua]` table in
   `pyproject.toml`), add a check step:

   ```toml
   [tool.madoqua]
   extend_check = [
     { name = "prose-lint", cmd = "prose-lint hook", on = ["*.md", "*.markdown"], timeout_s = 5 },
   ]
   ```

   madoqua prints a step's output only when it fails, and the hook always exits 0,
   so warnings stay hidden for now (madoqua#19). Without madoqua, run:

   ```
   uv run prose-lint install-hook
   ```

4. Get a baseline before the first commit:

   ```
   uv run prose-lint check .
   ```

   The first hook run starts the spaCy server and skips that commit. Later
   commits get warnings.

5. Record it. Add one line to `CLAUDE.md`: "When a commit prints prose-lint
   warnings, run `uv run prose-lint guide triage` and rewrite the flagged prose."

### Done looks like

`uv run prose-lint guide` names `triage` on its first line, and
`uv run prose-lint check .` prints `file:line:col` lines or nothing.

### Do not

- Do not make the hook blocking (`check --strict` in a hook). The design is
  warn-only.
- Do not copy thresholds into `prose-lint.toml` unless you mean to change them;
  see `uv run prose-lint guide tune`.

next: `uv run prose-lint check .`
