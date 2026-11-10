# prose-lint

Fast, soft feedback on Markdown docs that are hard to read. It targets the habits
of text written by Claude. Warnings go back to Claude so it can rewrite the text.
**Warnings never block a commit.**

Agents: start with the built-in guide. It picks setup or triage from the repo state.

```
uvx prose-lint@latest guide
```

Sample output:

```
docs/setup.md:12:1 R1 Sentence has 31 words; consider splitting.
docs/setup.md:14:22 R2 Stack of 4 nouns ("pipeline configuration validation error"); rephrase with a verb or preposition.
docs/setup.md:15:9 R3 Habit word "leverage"; try: use.
docs/setup.md:18:5 R4 "performs validation" hides the verb; try "validate".
```

## How it works

- **Local spaCy server.** A small FastAPI process keeps `en_core_web_sm` loaded on
  `127.0.0.1:8737`. The hook starts it on first use and reuses it after that. It
  exits after 4 hours without requests.
- **Commit hook client.** It sends only the staged Markdown files to the server and
  prints the warnings. It uses only the standard library and starts in under 0.1 s.
- **Fail open.** If the server is down, the hook starts it and skips this commit. If
  the server takes longer than 300 ms, the hook skips. Either way it prints nothing.
- **Output for Claude.** One warning per line as `file:line:col rule-id message`, or
  JSON with `--format json`.

## Install

Add it to the repo's dev dependencies, so the hook finds it in `.venv`:

```
uv add --dev prose-lint
cp /path/to/prose-linter/prose-lint.toml .   # optional; every key has a default
```

### The spaCy model

spaCy models are not on PyPI, so `en_core_web_sm` 3.8.0 is not a dependency. On
first use, `check`, `stats`, `measure` and the server download the wheel once
(~13 MB) and check its SHA-256. They unpack it to
`~/.cache/prose-lint/models/`, outside any virtualenv, so every `uvx` run and
venv shares one copy. This needs no pip. The hook client never downloads; it
skips commits while the server starts.

Offline, install the model into the environment instead:

```
uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
```

Or set `PROSE_LINT_MODEL_WHEEL` to a local copy (or mirror URL) of that wheel.

### With madoqua (the main path)

Add a check step that wakes on staged Markdown. madoqua appends the matched files:

```toml
[tool.madoqua]
extend_check = [
  { name = "prose-lint", cmd = "prose-lint hook", on = ["*.md", "*.markdown"], timeout_s = 5 },
]
```

**Gap:** madoqua prints a step's output only when the step fails, and
`prose-lint hook` always exits 0. So the warnings stay hidden until madoqua gets
a warn-only step mode that prints output without blocking
([madoqua#19](https://github.com/mojzis/madoqua/issues/19)).

### Without madoqua

```
prose-lint install-hook   # adds one warn-only line to the pre-commit hook
```

`install-hook` follows `core.hooksPath`. It puts its line right after the shebang, so
it runs even when the rest of the hook ends in `exec`.

## Commands

| Command | What it does |
| --- | --- |
| `prose-lint guide [setup\|triage\|tune]` | Print instructions for an agent. With no topic it picks one from the current directory. |
| `prose-lint check PATH...` | Lint files or folders in-process, no server. `--format json`, `--strict` exits 1 on warnings. |
| `prose-lint stats PATH...` | Warnings per 1,000 words per file and rule, one table per path. |
| `prose-lint measure PATH...` | Readability stats for whole docs. Writes Parquet tables and `report.md` to `--out` (default `stats/`). Needs the `measure` extra. |
| `prose-lint hook [FILE...]` | What the git hook runs. Lints the given files, or asks git for the staged docs. `--wait 10` waits for the server instead of skipping. |
| `prose-lint serve` | Run the server in the foreground. `--idle-timeout 0` keeps it up. |
| `prose-lint stop` | Stop the server, for example after an upgrade. |

The hook replaces a server whose code differs from its own. It compares a hash of the
package source, so upgrades and local edits take effect. The commit that finds the
mismatch is skipped.

Environment variables:

- `PROSE_LINT_VERBOSE=1` prints why the hook skipped.
- `PROSE_LINT_DISABLE=1` turns the hook off.
- `PROSE_LINT_PORT` and `PROSE_LINT_TIMEOUT_MS` override the config.
- `PROSE_LINT_MODEL_WHEEL` is a path or URL to fetch the spaCy model wheel from.

The server log is in `~/.cache/prose-lint/server.log`.

## Rules

| ID | Name | Warns when | Strong when |
| --- | --- | --- | --- |
| R1 | `long-sentence` | a sentence has more than 25 words | more than 35 |
| R2 | `noun-stack` | 4 or more nouns in a row modify each other | 5 or more |
| R3 | `habit-word` | a word from the habit list appears | more than 2 in one paragraph |
| R4 | `nominalization` | a weak verb takes an abstract noun ("performs validation of") | the sentence also has 4 or more abstract nouns |

Details:

- **All rules** skip code blocks, inline code, tables, front matter, HTML and link
  targets. List items that hold only an identifier, like `- max_retries`, are skipped
  too.
- **Headings** get R3 only.
- **R2** ignores runs made only of proper nouns, like "GitHub Actions CI". It also
  ignores runs with more than one proper noun (`max_proper_nouns`), like "Claude Code
  conversation logs". Inline code breaks a run, and a hyphenated word like
  "event-store" counts as one noun. The threshold is 4, not 3: at 3 it flagged plain
  technical terms like "Unix domain socket" in real docs. At 5 it would miss every true
  stack the rollout found. The tagger often calls a verb a noun, so R2 drops these from
  a run before it counts:
  - a verb that opens a list item, sentence or labelled line: "Test line number
    accuracy", "Purpose: Validates crossword grid structure";
  - a plural before another noun, which ends a subject: "a header toggle pins
    light/dark", "Claude Code loads ancestor files";
  - a plural verb that the parser made the root of a verbless sentence, like "resets"
    in "The progress bar resets after a logout".

  The verb test uses the WordNet verb list in spaCy's lemmatizer.
<!-- prose-lint: disable-next R3 -->
- **R3** matches inflections, so "leveraging" counts as "leverage". The default list:
  comprehensive, robust, seamless, seamlessly, leverage, utilize, delve, crucial,
  streamline, ensure, facilitate, "in order to", "it is important to note",
  successfully, "solid foundation". "successfully" counts only right before a verb:
  "successfully implemented", not "runs successfully". Words in `ok_at_item_start`
  (default: ensure) are fine as the first word of a list item or checklist line, as in
  "- Ensure the build passes". "essential" is off the list. In real docs it mostly
  meant just that ("essential information").
- **R4** counts nouns that end in -tion, -sion, -ment, -ance, -ence or -ity. A stoplist
  removes concrete words like "function", "document" and "instance". A weak verb is
  flagged only when its noun comes from a verb, as "placement" comes from "place".
  "fraction" and "flexibility" have no verb, so nothing is hidden. For "be" and "have",
  the noun must also take "of" and not be counted. So "is the implementation of" is
  flagged, but "is one placement of" is not. "provide", "give" and "offer" are
  skipped when they hand something over. That means a recipient ("provides guidance to
  Claude Code") or a named deliverable ("provide image descriptions").

## Measuring whole docs

`prose-lint measure` reports how hard a set of docs is to read, and where the
hardest parts are. It never edits a doc.

```
uv add --dev "prose-lint[measure]"
uv run prose-lint measure docs/ --out stats/
```

It writes four files:

- `sentences.parquet`: one row per sentence, with file, line, column, section and
  source text. It counts words, passives, commas, parentheses, dashes,
  nominalizations and habit words. It also gives mean dependency distance, main
  verb position and the longest noun run.
- `sections.parquet` and `files.parquet`: sentence length as mean, median, p90 and
  max, and the share of sentences over 25 and 35 words. Readability as Flesch
  reading ease, Flesch-Kincaid grade, Gunning Fog and LIX. Part-of-speech shares and
  the noun-to-verb ratio. Nominalizations per 100 words, repeated 5-grams, and habit
  words per 1,000 words.
- `report.md`: medians and p90s, the 15 hardest files and sections, the 30 hardest
  sentences, and which metrics spread enough to make good lint thresholds.

It uses the same parser as the linter, and the R2 to R4 definitions of noun runs,
nominalizations and habit words. Headings only name sections. List items under 4
words are skipped. TextDescriptives computes readability, dependency distance,
part-of-speech shares and repetition.

### As a library

A docs server can load the model once and measure pages on request:

```python
from prose_lint.measure import Measurer
from prose_lint.measure_report import render

measurer = Measurer()  # loads spaCy once; reuse it
result = measurer.measure({"guide.md": text})  # {path: markdown}
result.files.row(0, named=True)  # dict of file metrics
result.sentences.sort("words", descending=True).head(5)
render(result, min_words=100)  # the report as Markdown
```

`result.sentences`, `.sections` and `.files` are Polars data frames.

## Configuration

Put one `prose-lint.toml` at the repo root. The [sample in this repo](prose-lint.toml)
lists every key with its default.

To turn rules off inside a document:

```markdown
<!-- prose-lint: disable R2 -->        off until enable or end of file
<!-- prose-lint: enable R2 -->
<!-- prose-lint: disable-next R1 R3 --> off for the next block only
<!-- prose-lint: disable -->           all rules
```

Rules can be named by ID (`R2`) or by name (`noun-stack`).

## Feedback loop with Claude

Add this to the `CLAUDE.md` of a repo that uses the hook:

> When a commit prints `prose-lint` warnings, rewrite the flagged prose and commit
> again. Split long sentences, turn noun stacks and nominalizations into verbs, and
> replace habit words with plain ones. Use `<!-- prose-lint: disable-next Rn -->` only
> where a warning is wrong, and say why.

For a whole document, run `prose-lint check --format json doc.md`, give Claude the
result, and ask for a rewrite. The `prose-rewrite` skill in `.claude/skills/` does this
loop. Then check the result with people, not just with the linter.

## Measuring success

- **Density.** Warnings per 1,000 words before and after a rewrite:
  `prose-lint stats before/ after/`.
- **Human rating.** A quick 1 to 5 readability score on the test set.
- **Noise.** How often people disable each rule. Remove the noisy ones.

The baseline test set lives in [`corpus/`](corpus/):

- `bad/` and `good/` hold synthetic docs that read badly and well.
  `tests/test_corpus.py` checks that bad docs score far worse than good ones.
- `toolbox/` holds the real docs of the aesop tools (gerenuk, madoqua, biston,
  zorilla, coati, ty-find). They are unlabeled. The test checks that R2 to R4 stay
  under 1 per 1,000 words there, which catches rules that start flagging normal
  prose. `scripts/sync-toolbox-corpus.sh` refreshes the copy.

Swap in 10 to 20 real hard-to-read docs from your team for `bad/` before tuning
further.

Current numbers (warnings per 1,000 words):

| Set | Words | R1 | R2 | R3 | R4 | Total |
| --- | --- | --- | --- | --- | --- | --- |
| bad | 2,698 | 7.4 | 3.3 | 41.9 | 8.5 | 61.2 |
| good | 1,235 | 0 | 0 | 0.8 | 0 | 0.8 |
| toolbox | 51,529 | 9.0 | 0.1 | 0.0 | 0.2 | 9.3 |

## Roadmap

1. ~~Baseline test set~~ (placeholders; swap in real docs)
2. ~~Four starter rules~~
3. ~~Commit hook in warn-only mode~~
4. Feedback loop: rewrite with Claude, then ask people whether the result reads better.
5. Expand: try passive voice per paragraph, late main verb, deep nesting, too many
   parentheses, undefined acronyms, repeated openings, summary filler and Flesch score.
   Add an optional LLM judge in CI.
6. Port the useful rules to Rust (harper-core and Weir) if speed or distribution
   becomes a problem.

## Development

```
uv sync
uv run madoqua install
uv run poe check
```

### Releasing

Pushing a `vX.Y.Z` tag runs `.github/workflows/release.yml`. It builds, runs
`twine check`, publishes to PyPI by trusted publishing and creates a GitHub
release.

1. Bump `version` in `pyproject.toml` and commit.
2. `git tag vX.Y.Z` (the same version) and `git push origin vX.Y.Z`.
