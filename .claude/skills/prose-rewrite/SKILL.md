---
name: prose-rewrite
description: Rewrite a Markdown doc so it is easier to read, driven by lepisma warnings. Use when the user asks to clean up, simplify or de-Claude a doc, or when a commit prints lepisma warnings.
---

# Rewrite a doc with lepisma

1. Run `lepisma check --format json <file>` and note `summary.per_1000_words`.
2. Rewrite only the flagged prose. Keep the meaning, facts, headings, code and links.
   - R1 long sentence: split it. One idea per sentence.
   - R2 noun stack: unpack it with a verb or a preposition
     ("error handling for config validation", or better, "when validation fails, ...").
   - R3 habit word: use the suggestion, or delete the word if the sentence still holds.
   - R4 nominalization: use the hidden verb ("performs validation of X" → "validates X").
3. Run the check again. Repeat until warnings stop dropping. Zero is not the goal.
4. Where a warning is wrong, leave the text and add
   `<!-- lepisma: disable-next Rn -->` above the block. Tell the user why.
5. Report: density before → after, and any rule that looked noisy. Noisy rules are
   input for tuning `lepisma.toml`.
