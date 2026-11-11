## Tune: config, thresholds and exit codes

Config is `lepisma.toml`, found by walking up from the current directory.
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
# more proper nouns than this and the run is a name ("Google Cloud Platform account")
max_proper_nouns = {{noun_stack.max_proper_nouns}}

[rules.habit-word]                 # R3
# words = [...]                    # replaces the built-in list
# extra_words = ["paradigm"]       # adds to it
# suggestions = { paradigm = "model" }
max_per_paragraph = {{habit_words.max_per_paragraph}}
# ok_at_item_start = ["ensure"]   # fine as a list item's first word

[rules.nominalization]             # R4
# weak_verbs = [...]
# extra_stoplist = ["migration"]   # concrete words that end in -tion etc.
min_length = {{nominalization.min_length}}
max_per_sentence = {{nominalization.max_per_sentence}}

[rules.late-verb]                  # R5
max_words_before = {{late_verb.max_words_before}}
strong_words_before = {{late_verb.strong_words_before}}

[rules.vague-this]                 # R6
# words = ["this", "these"]

[rules.tidy-summary]               # R7
# openers = ["overall", "in summary", "this ensures", ...]

[rules.interruption-load]          # R8
# dashes, parentheses, semicolons and mid-sentence colons in one sentence
warn_at = {{interruption_load.warn_at}}
strong_at = {{interruption_load.strong_at}}
# a dash or colon after this few words marks a label ("`name` - text")
label_words = {{interruption_load.label_words}}
# a parenthesis with fewer words is a gloss ("`-d` (docs)"), not an aside
min_paren_words = {{interruption_load.min_paren_words}}

[rules.contrast-frame]             # R9, judged per document
# "X, not Y", "not X but Y", "rather than", "isn't X. It's Y"
min_count = {{contrast_frame.min_count}}             # fewer frames than this never warn
max_per_1000 = {{contrast_frame.max_per_1000}}        # strong at twice this

[rules.undefined-term]             # R10, judged per document
# known_acronyms = [...]           # replaces the built-in list
# extra_known = ["LSP"]            # acronyms that need no expansion in this repo
# also flag rare words that a document uses often and never defines
rare_terms = {{undefined_term.rare_terms}}
min_uses = {{undefined_term.min_uses}}                       # uses before a rare word counts
# known_terms = ["worktree"]       # rare words that need no definition here

[rules.emphasis]                   # R11, judged per document and per family
# sincerity = ["genuinely", "exactly", "deliberately", "quietly", "silently"]
# figurative = ["seam", "verdict", "load-bearing", "shape", "rung", "floor", ...]
min_count = {{emphasis.min_count}}             # fewer hits than this never warn
max_per_1000 = {{emphasis.max_per_1000}}        # strong at twice this
```

Rules can be named by ID (`R2`) or name (`noun-stack`), here and in comments:
`<!-- lepisma: disable R2 -->`, `enable R2`, `disable-next R1 R3`, or
`disable` for all rules.

### Environment

`LEPISMA_VERBOSE=1` prints why the hook skipped. `LEPISMA_PORT` and
`LEPISMA_TIMEOUT_MS` override the config. The server log is
`~/.cache/lepisma/server.log`.

### Exit codes

- `lepisma check`: 0; 1 with `--strict` when there are warnings.
- `lepisma hook`: always 0.
- `lepisma measure`: 1 when no docs are found, 2 without the `measure` extra.
- `lepisma stop`: 1 when no server is running.
- `lepisma guide`: 0; 1 only if stdout cannot be written.

### Changing a threshold

1. Measure first, on docs you trust to be good and docs you know are bad:

   ```
   uv run lepisma stats docs/
   ```

2. Change one key in `lepisma.toml` and run the same command again.
3. Keep the change only if good docs drop and bad docs stay flagged. One noisy
   file is a case for a `disable-next` comment, not a new threshold.
4. After a code change to the linter, run `uv run lepisma stop` so the hook
   starts a fresh server (it also replaces a stale one on its own).

next: `uv run lepisma stats docs/`
