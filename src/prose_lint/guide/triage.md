## Triage: prose-lint printed warnings

Each warning is one line: `file:line:col rule-id message`. Warnings never block a
commit; the commit already went ahead. Your job is to rewrite the flagged prose.

To see every warning in a file, without the server:

```
uv run prose-lint check --format json docs/setup.md
```

### What each rule means

<!-- prose-lint: disable R2 R3 R4 -->
- **R1 long-sentence**: over {{long_sentence.max_words}} words, strong over {{long_sentence.strong_words}}.
  Split it into two or three sentences.
- **R2 noun-stack**: {{noun_stack.min_nouns}} or more nouns modify each other
  ("pipeline configuration validation error"). Unpack it with a verb or a
  preposition: "the error when the pipeline config fails to validate".
- **R3 habit-word**: a filler word such as "leverage" or "robust". The message
  names a plainer word; use it, or cut the word.
- **R4 nominalization**: a weak verb hides the real one ("performs validation of").
  Use the verb the message suggests: "validates".
<!-- prose-lint: enable R2 R3 R4 -->

### Remedy ladder (take the first rule that applies)

1. Rewrite the sentence as the message suggests. This is the answer almost always.
2. The flagged text is really code, a path or a name: wrap it in backticks. Inline
   code is skipped and breaks noun stacks.
3. The text is data or a quote that must stay as is. Put it in a code block or
   a table; the linter skips both.
4. The rule is wrong for this one sentence: add
   `<!-- prose-lint: disable-next R2 -->` on the line before the block, and say
   why in your reply or commit message.
5. A rule is wrong across this repo: tell a human. Changing thresholds is a policy
   call; see `uv run prose-lint guide tune`.

### Done looks like

`uv run prose-lint check docs/setup.md` prints nothing and exits 0.

### Do not

- Do not wrap prose in backticks or code blocks just to hide it from the linter.
- Do not add `disable` comments to get rid of warnings you did not read.
- Do not raise a threshold in `prose-lint.toml` to pass one file.
- Do not set `PROSE_LINT_DISABLE=1` or remove the hook line.
- Do not swap a habit word for a synonym that is just as vague.

next: `uv run prose-lint check --format json <file>`
