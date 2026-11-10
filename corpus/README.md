# Prose linter test corpus

These documents are synthetic placeholders written to exercise the four rules (long sentences, noun stacks, Claude habit words, nominalizations) and the Markdown handling. The team should replace or extend them with 10-20 real hard-to-read docs plus a few that read well, to serve as the Phase 1 baseline. Files under `bad/` should score clearly worse than files under `good/`.

`toolbox/` is different: real docs copied from the aesop tool repos by
`scripts/sync-toolbox-corpus.sh`. They are unlabeled and serve as a check against
false positives on normal technical prose.
