# lepisma

Fast, soft feedback on Markdown docs that are hard to read. It targets the habits
of text written by Claude. Warnings go back to Claude so it can rewrite the text.
**Warnings never block a commit.**

The name: *Lepisma saccharina* is the silverfish, which eats paper and chews
through books.

Agents: start with the built-in guide. It picks setup or triage from the repo state.

```
uvx lepisma@latest guide
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
uv add --dev lepisma
cp /path/to/lepisma/lepisma.toml .   # optional; every key has a default
```

### The spaCy model

spaCy models are not on PyPI, so `en_core_web_sm` 3.8.0 is not a dependency. On
first use, `check`, `stats`, `measure` and the server download the wheel once
(~13 MB) and check its SHA-256. They unpack it to
`~/.cache/lepisma/models/`, outside any virtualenv, so every `uvx` run and
venv shares one copy. No pip is needed. The hook client never downloads; it
skips commits while the server starts.

Offline, install the model into the environment instead:

```
uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
```

Or set `LEPISMA_MODEL_WHEEL` to a local copy (or mirror URL) of that wheel.

### With madoqua (the main path)

Add a check step that wakes on staged Markdown. madoqua appends the matched files:

```toml
[tool.madoqua]
extend_check = [
  { name = "lepisma", cmd = "lepisma hook", on = ["*.md", "*.markdown"], timeout_s = 5 },
]
```

**Gap:** madoqua prints a step's output only when the step fails, and
`lepisma hook` always exits 0. So the warnings stay hidden until madoqua gets
a warn-only step mode that prints output without blocking
([madoqua#19](https://github.com/mojzis/madoqua/issues/19)).

### Without madoqua

```
lepisma install-hook   # adds one warn-only line to the pre-commit hook
```

`install-hook` follows `core.hooksPath`. It puts its line right after the shebang, so
it runs even when the rest of the hook ends in `exec`.

## Commands

| Command | What it does |
| --- | --- |
| `lepisma guide [setup\|triage\|tune]` | Print instructions for an agent. With no topic it picks one from the current directory. |
| `lepisma check PATH...` | Lint files or folders in-process, no server. `--format json`, `--strict` exits 1 on warnings. |
| `lepisma stats PATH...` | Warnings per 1,000 words per file and rule, one table per path. |
| `lepisma measure PATH...` | Readability stats for whole docs. Writes Parquet tables and `report.md` to `--out` (default `stats/`). Needs the `measure` extra. |
| `lepisma hook [FILE...]` | What the git hook runs. Lints the given files, or asks git for the staged docs. `--wait 10` waits for the server instead of skipping. |
| `lepisma serve` | Run the server in the foreground. `--idle-timeout 0` keeps it up. |
| `lepisma stop` | Stop the server, for example after an upgrade. |

The hook replaces a server whose code differs from its own. It compares a hash of the
package source, so upgrades and local edits take effect. The commit that finds the
mismatch is skipped.

Environment variables:

- `LEPISMA_VERBOSE=1` prints why the hook skipped.
- `LEPISMA_DISABLE=1` turns the hook off.
- `LEPISMA_PORT` and `LEPISMA_TIMEOUT_MS` override the config.
- `LEPISMA_MODEL_WHEEL` is a path or URL to fetch the spaCy model wheel from.

The server log is in `~/.cache/lepisma/server.log`.

## Rules

| ID | Name | Warns when | Strong when |
| --- | --- | --- | --- |
| R1 | `long-sentence` | a sentence has more than 25 words | more than 35 |
| R2 | `noun-stack` | 4 or more nouns in a row modify each other | 5 or more |
| R3 | `habit-word` | a word from the habit list appears | more than 2 in one paragraph |
| R4 | `nominalization` | a weak verb takes an abstract noun ("performs validation of") | the sentence also has 4 or more abstract nouns |
| R5 | `late-verb` | more than 14 words come before the main verb | more than 20 |
| R6 | `vague-this` | a bare "This" or "These" is the subject of an action verb ("This allows ...") | never |
| R7 | `tidy-summary` | a paragraph's last sentence opens with "Overall", "In summary", "This ensures" and the like | never |
| R8 | `interruption-load` | one sentence holds 2 or more dashes, parentheses, semicolons or mid-sentence colons | 3 or more |
| R9 | `contrast-frame` | a document holds 3 or more frames like "X, not Y", and more than 4 per 1,000 words | more than 8 per 1,000 words |
| R10 | `undefined-term` | an acronym is not spelled out near its first use | never |
| R11 | `emphasis` | a document holds 3 or more sincerity words, or 3 or more figurative terms, and more than 3 per 1,000 words | more than 6 per 1,000 words |

Details:

- **All rules** skip code blocks, inline code, tables, front matter, HTML and link
  targets. List items that hold only an identifier, like `- max_retries`, are skipped
  too.
- **Headings** get R3, R9, R10 and R11 only. R7 looks at paragraphs and quotes only.
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
<!-- lepisma: disable-next R3 -->
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
- **R5** counts words up to the first word of the main verb group, so "will" in
  "will be deleted". A long "When ..." or "If ..." clause in front counts, which is
  the point. The parser often hangs the first clause under a later one. So any
  clause with its own subject and no "if" or "which" in front counts as a main
  clause. The count restarts after a label mark (":", " - ", em dash) or a semicolon.
  Sentences with no verb at the root, like list fragments, are skipped. At 12 words
  it flagged 2.4 per 1,000 words in the toolbox docs; at 14 it is under 1.
<!-- lepisma: disable-next R3 -->
- **R6** skips "This flag allows", where the noun names the referent. It also skips
  "This is", a plain linking verb. A paragraph's closing "This ensures ..." is left to R7.
- **R7** needs a paragraph of two or more sentences. The opener list is
  `openers` in the config.
- **R8** counts em dashes, `--`, spaced en dashes, parentheses, semicolons and
  colons that have words on both sides. A pair of dashes counts as two. It skips
  marks that do not interrupt:
  - a dash or colon after a label of up to `label_words` words, as in "`name` -
    the symbol to find". A bold label can be any length.
  - a parenthesis with fewer than `min_paren_words` words, as in "`-d` (docs)".
  - a colon that ends the sentence or only introduces code.
  - a semicolon that ends a list item.
  - any mark inside double quotes, since quoted text is an example.

<!-- lepisma: disable-next R9 -->
- **R9** judges a whole document and warns once, at the first frame. One contrast
  is fine, and many are a habit. It matches "not X but Y", "X, not Y", "rather
  than", and a negation that the next sentence corrects: "It isn't a gate. It's
  a report." Headings count. It leaves out "not only X but also Y", which adds,
  and "does not X, but Y", which concedes. A block that disables R9 is left out
  of the count.

- **R10** warns once per acronym, at its first use. An acronym is 2 to 6 capital
  letters outside code. It passes when words with the same initials appear by the
  end of the next block, as in "Language Server Protocol (LSP)". It skips a short
  list of acronyms that technical readers know (`known_acronyms`, extended by
  `extra_known`). It also skips capitals whose lowercase form is a common English
  word, like "PATH" and "NOT".

  `rare_terms = true` adds a second check. It flags a word that is not in the
  common-word list, appears `min_uses` times or more, and is never
  defined. A definition is "X is", "X means", "X (...)", "(X)", "called X", "X, a
  ..." or a glossary line. Words in the first heading, words that the document
  also writes as code, and `known_terms` are skipped. The check is off by default.
  In the toolbox docs two thirds of its hits were jargon that the readers know,
  such as "workspace", "stderr" and "docstring".

  The word list is `data/common_words.txt.gz`, about 170 kB. It holds 64,000
  common English words with their inflections, taken from
  [SCOWL](http://wordlist.aspell.net/) up to size 50. SCOWL has a permissive
  licence in the MIT style, and its notice ships as `data/common_words.LICENSE`.
  Only the server and `check` read the list. The hook client does not.

<!-- lepisma: disable-next R11 -->
- **R11** counts two word families, each on its own, and warns once per family at
  the first hit. Sincerity words claim what the text should show: genuinely,
  exactly, deliberately, quietly, silently. Figurative terms stand in for a plain
  name: seam, verdict, load-bearing, shape, rung, floor, land, surface, wire,
  drift. Inflections match, so "seams" and "wired" count. Many of these words
  also have a literal use, like "exactly one line". So R11 judges the density per
  document, and one or two uses never warn. A figurative term that the document
  introduces with "A seam is ..." or "called a seam" is a name and is left out.
  Both lists are config keys. R3 is unchanged: its list holds filler that is
  wrong on every use.

  About half of the R8 hits in the toolbox docs are in sentences of 25 words or
  fewer, which R1 never sees.

## Measuring whole docs

`lepisma measure` reports how hard a set of docs is to read, and where the
hardest parts are. It never edits a doc.

```
uv add --dev "lepisma[measure]"
uv run lepisma measure docs/ --out stats/
```

It writes four files:

- `sentences.parquet`: one row per sentence, with file, line, column, section and
  source text. It counts words, passives, commas, parentheses, dashes,
  nominalizations and habit words. It also gives mean dependency distance, main
  verb position and the longest noun run.
- `sections.parquet` and `files.parquet`: sentence length as mean, median, p90 and
  max, and the share of sentences over 25 and 35 words. Readability as Flesch
  reading ease, Flesch-Kincaid grade, Gunning Fog and the LIX index. Part-of-speech shares and
  the noun-to-verb ratio. Nominalizations per 100 words, repeated 5-grams, and habit
  words per 1,000 words.
- `report.md`: medians and p90s, the 15 hardest files and sections, the 30 hardest
  sentences, and which metrics spread enough to make good lint thresholds.

The tables also count the patterns that current Claude models lean on. Each is
a column per sentence, and a rate per 1,000 words per section and file:

- Interrupters: em dashes, semicolons, parentheses and colons in the middle of a
  sentence. `share_interrupted` is the share of sentences with two or more.
  A dash or colon after a short label is not counted.
- Contrast frames: "not X but Y", "X, not Y", "isn't X. It's Y" and "rather than".
  Headings are counted too, in `heading_contrast_frames`.
- Emphasis: sincerity words ("genuinely", "exactly"), importance flags ("this
  matters"), figurative terms ("seam", "verdict") and bold spans per block.
- Compression: arrows in prose, compounds of three or more hyphenated words, and
  paragraph sentences with no verb or no subject.
- Short sentences that follow a long one, sentence-final ", making ..." clauses,
  and things that "want" or "know".
- `acronyms_unexpanded` and `acronym_list` per file: acronyms that are not spelled
  out near their first use.

These columns measure. They are not rules yet. `signals.py` defines them, and
[Background](#background) lists the research behind them.

It uses the same parser as the linter, and the R2 to R4 definitions of noun runs,
nominalizations and habit words. Headings only name sections. List items under 4
words are skipped. Readability, dependency distance, part-of-speech shares and
repetition use TextDescriptives' formulas, ported into `textstats.py`.

### As a library

A docs server can load the model once and measure pages on request:

```python
from lepisma.measure import Measurer
from lepisma.measure_report import render

measurer = Measurer()  # loads spaCy once; reuse it
result = measurer.measure({"guide.md": text})  # {path: markdown}
result.files.row(0, named=True)  # dict of file metrics
result.sentences.sort("words", descending=True).head(5)
render(result, min_words=100)  # the report as Markdown
```

`result.sentences`, `.sections` and `.files` are Polars data frames.

## Configuration

Put one `lepisma.toml` at the repo root. The [sample in this repo](lepisma.toml)
lists every key with its default.

To turn rules off inside a document:

```markdown
<!-- lepisma: disable R2 -->        off until enable or end of file
<!-- lepisma: enable R2 -->
<!-- lepisma: disable-next R1 R3 --> off for the next block only
<!-- lepisma: disable -->           all rules
```

Rules can be named by ID (`R2`) or by name (`noun-stack`).

## Feedback loop with Claude

Add this to the `CLAUDE.md` of a repo that uses the hook:

> When a commit prints `lepisma` warnings, rewrite the flagged prose and commit
> again. Split long sentences, turn noun stacks and nominalizations into verbs, and
> replace habit words with plain ones. Use `<!-- lepisma: disable-next Rn -->` only
> where a warning is wrong, and say why.

For a whole document, run `lepisma check --format json doc.md`, give Claude the
result, and ask for a rewrite. The `prose-rewrite` skill in `.claude/skills/` does this
loop. Then check the result with people, not just with the linter.

## Measuring success

- **Density.** Warnings per 1,000 words before and after a rewrite:
  `lepisma stats before/ after/`.
- **Human rating.** A quick 1 to 5 readability score on the test set.
- **Noise.** How often people disable each rule. Remove the noisy ones.

The baseline test set lives in [`corpus/`](corpus/):

- `bad/` and `good/` hold synthetic docs that read badly and well.
  `tests/test_corpus.py` checks that bad docs score far worse than good ones.
- `toolbox/` holds the real docs of the aesop tools (gerenuk, madoqua, biston,
  zorilla, coati, ty-find). They are unlabeled. The test checks that R2 to R4 stay
  under 1 per 1,000 words there, which catches rules that start flagging normal
  prose. For R8 and later the test runs the other way. Those rules target how
  Claude writes now, so the toolbox docs must score above 3 per 1,000 words and
  the good docs below 1. `scripts/sync-toolbox-corpus.sh` refreshes the copy.

Swap in 10 to 20 real hard-to-read docs from your team for `bad/` before tuning
further.

Current numbers (warnings per 1,000 words):

| Set | Words | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bad | 2,698 | 7.4 | 3.3 | 41.9 | 8.5 | 0 | 0 | 3.3 | 0.4 | 0 | 0.4 | 0 | 65.2 |
| good | 1,235 | 0 | 0 | 0.8 | 0 | 0 | 0 | 0 | 0 | 0 | 0.8 | 0 | 1.6 |
| toolbox | 51,463 | 9.0 | 0.1 | 0.0 | 0.2 | 0.8 | 0.2 | 0.0 | 3.9 | 0.6 | 1.2 | 0.7 | 16.7 |

R9 and later warn once per document, so their numbers stay small. R9 flags 30 of
the 115 toolbox docs. R11 flags 26 for figurative terms and 8 for sincerity words.

The same sets, measured for the newer patterns with `lepisma measure` (per 1,000
words unless noted):

| Measure | bad | good | toolbox |
| --- | --- | --- | --- |
| Em dashes | 1.2 | 0 | 10.9 |
| All interrupters | 2.8 | 2.7 | 25.3 |
| Sentences with 2 or more interrupters | 1 | 0 | 203 of 3,358 |
| Contrast frames | 0.4 | 0.9 | 4.8 |
| Figurative terms | 0 | 0 | 5.0 |
| Sincerity words | 0 | 0 | 2.2 |
| Bold spans | 0.8 | 0.9 | 10.3 |
| Files with an unexpanded acronym | 2 of 10 | 3 of 6 | 47 of 114 |

The rules catch the old corporate style in `bad/`. The toolbox docs are real Claude
output and score low on R1 to R7, yet they carry ten times the interrupters of
either synthetic set. The next rules target that gap.

## Roadmap

1. ~~Baseline test set~~ (placeholders, to be swapped for real docs)
2. ~~Four starter rules~~
3. ~~Commit hook in warn-only mode~~
4. Feedback loop: rewrite with Claude, then ask people whether the result reads better.
5. Expand: ~~late main verb~~, ~~vague "this"~~, ~~summary filler~~. Next: passive
   voice per paragraph, deep nesting, too many parentheses, undefined acronyms,
   repeated openings and Flesch score.
   Add an optional large language model (LLM) judge in CI.
6. Port the useful rules to Rust (harper-core and Weir) if speed or distribution
   becomes a problem.

## Background

The goal is prose that people find easy to read. It is not AI detection. A
pattern earns a rule only if it costs the reader effort. These sources describe
the patterns and how others handle them:

- [Prompting Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5):
  Anthropic's own notes on how the model writes and how to steer it.
- [AI Tells](https://graphite.io/five-percent/research/ai-tells-opus-5-5-update):
  Graphite's counts of the constructions that mark model prose, with data.
- [Do LLMs write like humans?](https://arxiv.org/abs/2410.16107) by Reinhart et
  al.: grammar and style features that differ between model and human text.
- [tropes.fyi](https://tropes.fyi/directory): a directory of named habits.
- [claudeisms](https://github.com/archiewood/claudeisms): a word list.
- [vale-agent-prose](https://github.com/dteirney/vale-agent-prose) and
  [vale-llm-slop](https://github.com/Syntaf/vale-llm-slop): Vale rule sets for the
  same problem.
- [claude-code issue 77136](https://github.com/anthropics/claude-code/issues/77136):
  a user report on the current style.

Word lists move the problem. Banned words drop and unlisted constructions rise.
So lepisma prefers checks on density and structure to longer lists.

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
