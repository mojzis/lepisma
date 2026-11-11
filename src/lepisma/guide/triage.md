## Triage: lepisma printed warnings

Each warning is one line: `file:line:col rule-id message`. Warnings never block a
commit; the commit already went ahead. Your job is to rewrite the flagged prose.

To see every warning in a file, without the server:

```
uv run lepisma check --format json docs/setup.md
```

### What each rule means

<!-- lepisma: disable R2 R3 R4 R5 R6 R7 R8 R9 R10 R11 -->
- **R1 long-sentence**: over {{long_sentence.max_words}} words, strong over {{long_sentence.strong_words}}.
  Split it into two or three sentences.
- **R2 noun-stack**: {{noun_stack.min_nouns}} or more nouns modify each other
  ("pipeline configuration validation error"). Unpack it with a verb or a
  preposition: "the error when the pipeline config fails to validate".
- **R3 habit-word**: a filler word such as "leverage" or "robust". The message
  names a plainer word; use it, or cut the word.
- **R4 nominalization**: a weak verb hides the real one ("performs validation of").
  Use the verb the message suggests: "validates".
- **R5 late-verb**: over {{late_verb.max_words_before}} words before the main verb.
  Put the subject and verb first; move a long "When ..." clause after them.
- **R6 vague-this**: "This allows ..." with no noun after "This". Name the thing
  ("This cache allows ...") or make the actor the subject ("The cache lets ...").
- **R7 tidy-summary**: a paragraph ends with "Overall, ..." or "This ensures ...".
  Cut the sentence, or replace it with a fact the paragraph has not stated.
- **R8 interruption-load**: {{interruption_load.warn_at}} or more dashes, parentheses, semicolons or
  mid-sentence colons in one sentence, strong at {{interruption_load.strong_at}}. Move each aside into its
  own sentence. Do not swap the marks for commas: read the result, and keep the
  aside where the split reads worse.
- **R9 contrast-frame**: one warning per document, at the first frame. The document
  holds {{contrast_frame.min_count}} or more frames like "X, not Y" or "rather than", and more than
  {{contrast_frame.max_per_1000}} per 1,000 words. The message lists the lines. Say what each thing is.
  Keep a contrast only where the reader would assume the opposite.
- **R10 undefined-term**: an acronym is not spelled out near its first use. Write
  the full name there, then the short form in parentheses: "Language Server
  Protocol (LSP)". With `rare_terms` on, it also flags a rare word used
  {{undefined_term.min_uses}} or more times and never defined. Define it at first use, or use a plainer word.
  If every reader of this repo knows the term, a human can add it to `extra_known`
  or `known_terms`.
- **R11 emphasis**: one warning per document and family, at the first hit. Sincerity
  words ("exactly", "genuinely") claim what the text should show: cut each one, or
  state the fact that backs it. Figurative terms ("seam", "verdict") stand in for
  a plain name: name the thing, or define the term once with "A seam is ...".
  A literal use is fine, and the count allows a few. Do not swap in another figure
  of speech.
<!-- lepisma: enable R2 R3 R4 R5 R6 R7 R8 R9 R10 R11 -->

### Remedy ladder (take the first rule that applies)

1. Rewrite the sentence as the message suggests. This is the answer almost always.
2. The flagged text is really code, a path or a name: wrap it in backticks. Inline
   code is skipped and breaks noun stacks.
3. The text is data or a quote that must stay as is. Put it in a code block or
   a table; the linter skips both.
4. The rule is wrong for this one sentence: add
   `<!-- lepisma: disable-next R2 -->` on the line before the block, and say
   why in your reply or commit message.
5. A rule is wrong across this repo: tell a human. Changing thresholds is a policy
   call; see `uv run lepisma guide tune`.

### Done looks like

`uv run lepisma check docs/setup.md` prints nothing and exits 0.

### Do not

- Do not wrap prose in backticks or code blocks just to hide it from the linter.
- Do not add `disable` comments to get rid of warnings you did not read.
- Do not raise a threshold in `lepisma.toml` to pass one file.
- Do not set `LEPISMA_DISABLE=1` or remove the hook line.
- Do not swap a habit word for a synonym that is just as vague.

next: `uv run lepisma check --format json <file>`
