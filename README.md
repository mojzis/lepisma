# prose-lint

Fast, soft feedback on Markdown docs that are hard to read. It targets the habits
of text written by Claude. Warnings go back to Claude so it can rewrite the text.
**Warnings never block a commit.**

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

```
uv tool install git+https://github.com/mojzis/prose-linter
cd your-repo
prose-lint install-hook          # adds one warn-only line to .git/hooks/pre-commit
cp /path/to/prose-linter/prose-lint.toml .   # optional; every key has a default
```

`install-hook` follows `core.hooksPath`. It puts its line right after the shebang, so
it runs even when the rest of the hook ends in `exec`.

## Commands

| Command | What it does |
| --- | --- |
| `prose-lint check PATH...` | Lint files or folders in-process, no server. `--format json`, `--strict` exits 1 on warnings. |
| `prose-lint stats PATH...` | Warnings per 1,000 words per file and rule, one table per path. |
| `prose-lint hook` | What the git hook runs. `--wait 10` waits for the server instead of skipping. |
| `prose-lint serve` | Run the server in the foreground. `--idle-timeout 0` keeps it up. |
| `prose-lint stop` | Stop the server, for example after an upgrade. |

The hook also stops a server that runs an older version, so upgrades take effect on
the next commit.

Environment variables:

- `PROSE_LINT_VERBOSE=1` prints why the hook skipped.
- `PROSE_LINT_DISABLE=1` turns the hook off.
- `PROSE_LINT_PORT` and `PROSE_LINT_TIMEOUT_MS` override the config.

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
- **R2** ignores runs made only of proper nouns, like "GitHub Actions CI". Inline code
  breaks a run, and a hyphenated word like "event-store" counts as one noun. The
  threshold is 4, not 3: at 3 it flagged plain technical terms like "Unix domain
  socket" in real docs.
<!-- prose-lint: disable-next R3 -->
- **R3** matches inflections, so "leveraging" counts as "leverage". The default list:
  comprehensive, robust, seamless, leverage, utilize, delve, crucial, essential,
  streamline, ensure, facilitate, "in order to", "it is important to note".
- **R4** counts nouns that end in -tion, -sion, -ment, -ance, -ence or -ity. A stoplist
  removes concrete words like "function", "document" and "instance". For "is", the noun
  must take "of", as in "is the implementation of".

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
| bad | 2,698 | 7.4 | 3.3 | 44.5 | 8.9 | 64.1 |
| good | 1,235 | 0 | 0 | 0.8 | 0 | 0.8 |
| toolbox | 51,529 | 9.0 | 0.2 | 0.1 | 0.2 | 9.5 |

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
git config core.hooksPath hooks   # prose-lint, then madoqua
uv run poe check
```
