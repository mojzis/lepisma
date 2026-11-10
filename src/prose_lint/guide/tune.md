## Tune: config, thresholds and exit codes

Config is `prose-lint.toml`, found by walking up from the current directory.
Every key is optional. Unknown keys and wrong types are errors.

### Keys and defaults

```toml
ignore = []                        # globs; filter docs found by walking a folder
extensions = [".md", ".markdown"]

[server]
port = {{server.port}}
# the hook skips when the server is slower than this
timeout_ms = {{server.timeout_ms}}

[rules.long-sentence]              # R1
enabled = true
max_words = {{long_sentence.max_words}}
strong_words = {{long_sentence.strong_words}}

[rules.noun-stack]                 # R2
min_nouns = {{noun_stack.min_nouns}}
strong_nouns = {{noun_stack.strong_nouns}}
# a run of only proper nouns ("GitHub Actions CI") is a name
ignore_all_propn = {{noun_stack.ignore_all_propn}}

[rules.habit-word]                 # R3
# words = [...]                    # replaces the built-in list
# extra_words = ["paradigm"]       # adds to it
# suggestions = { paradigm = "model" }
max_per_paragraph = {{habit_words.max_per_paragraph}}

[rules.nominalization]             # R4
# weak_verbs = [...]
# extra_stoplist = ["migration"]   # concrete words that end in -tion etc.
min_length = {{nominalization.min_length}}
max_per_sentence = {{nominalization.max_per_sentence}}
```

Rules can be named by ID (`R2`) or name (`noun-stack`), here and in comments:
`<!-- prose-lint: disable R2 -->`, `enable R2`, `disable-next R1 R3`, or
`disable` for all rules.

### Environment

`PROSE_LINT_VERBOSE=1` prints why the hook skipped. `PROSE_LINT_PORT` and
`PROSE_LINT_TIMEOUT_MS` override the config. The server log is
`~/.cache/prose-lint/server.log`.

### Exit codes

- `prose-lint check`: 0; 1 with `--strict` when there are warnings.
- `prose-lint hook`: always 0.
- `prose-lint measure`: 1 when no docs are found, 2 without the `measure` extra.
- `prose-lint stop`: 1 when no server is running.
- `prose-lint guide`: 0; 1 only if stdout cannot be written.

### Changing a threshold

1. Measure first, on docs you trust to be good and docs you know are bad:

   ```
   uv run prose-lint stats docs/
   ```

2. Change one key in `prose-lint.toml` and run the same command again.
3. Keep the change only if good docs drop and bad docs stay flagged. One noisy
   file is a case for a `disable-next` comment, not a new threshold.
4. After a code change to the linter, run `uv run prose-lint stop` so the hook
   starts a fresh server (it also replaces a stale one on its own).

next: `uv run prose-lint stats docs/`
