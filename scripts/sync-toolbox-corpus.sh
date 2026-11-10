#!/bin/sh
# Copy README.md and docs/ from the aesop toolbox repos into corpus/toolbox/.
# These are real docs, unlabeled: they guard against false positives.
# Usage: scripts/sync-toolbox-corpus.sh [dir containing the repos, default ~/git]
set -eu
src=${1:-$HOME/git}
dest=$(git rev-parse --show-toplevel)/corpus/toolbox
rm -rf "$dest"
for repo in gerenuk madoqua biston zorilla coati ty-find; do
    [ -d "$src/$repo" ] || { echo "skip $repo (not in $src)"; continue; }
    mkdir -p "$dest/$repo"
    cp "$src/$repo/README.md" "$dest/$repo/"
    (cd "$src/$repo" && find docs -name '*.md' -not -path '*/book/*' -not -path '*/plans/*') |
        while read -r f; do
            mkdir -p "$dest/$repo/$(dirname "$f")"
            cp "$src/$repo/$f" "$dest/$repo/$f"
        done
    echo "$repo: $(find "$dest/$repo" -name '*.md' | wc -l) files @ $(git -C "$src/$repo" rev-parse --short HEAD)"
done
