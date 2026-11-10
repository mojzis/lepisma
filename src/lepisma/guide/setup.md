## Setup: wire lepisma into this repository

lepisma gives soft warnings on hard-to-read Markdown. It runs as a warn-only
commit hook and never blocks a commit. Nothing here says it is set up yet: there
is no `lepisma.toml` and no `lepisma hook` step in `pyproject.toml`.

### Steps

1. Add it as a dev dependency, so the hook finds it in `.venv`:

   ```
   uv add --dev lepisma
   ```

   The first run downloads the spaCy model (~13 MB) into
   `~/.cache/lepisma/models/`. Offline, run
   `uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl`
   or set `LEPISMA_MODEL_WHEEL` to a local copy of that wheel.

2. Create `lepisma.toml` at the repo root. An empty file is valid; every key
   has a default. Add an `ignore` list for generated or vendored docs:

   ```toml
   ignore = ["CHANGELOG.md", "vendor/**"]
   ```

3. Hook it into commits. With madoqua (a `[tool.madoqua]` table in
   `pyproject.toml`), add a check step:

   ```toml
   [tool.madoqua]
   extend_check = [
     { name = "lepisma", cmd = "lepisma hook", on = ["*.md", "*.markdown"], timeout_s = 5 },
   ]
   ```

   madoqua prints a step's output only when it fails, and the hook always exits 0,
   so warnings stay hidden for now (madoqua#19). Without madoqua, run:

   ```
   uv run lepisma install-hook
   ```

4. Get a baseline before the first commit:

   ```
   uv run lepisma check .
   ```

   The first hook run starts the spaCy server and skips that commit. Later
   commits get warnings.

5. Record it. Add one line to `CLAUDE.md`: "When a commit prints lepisma
   warnings, run `uv run lepisma guide triage` and rewrite the flagged prose."

### Done looks like

`uv run lepisma guide` names `triage` on its first line, and
`uv run lepisma check .` prints `file:line:col` lines or nothing.

### Do not

- Do not make the hook blocking (`check --strict` in a hook). The design is
  warn-only.
- Do not copy thresholds into `lepisma.toml` unless you mean to change them;
  see `uv run lepisma guide tune`.

next: `uv run lepisma check .`
