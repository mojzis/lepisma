"""One row per prose chunk of each Markdown doc, as a Polars table.

A chunk is a paragraph, a whole list or a blockquote. Each row carries stable
IDs and hashes, so another tool can find passages that repeat within a repo or
across repos. This module only describes documents: it never compares chunks.

Needs the ``measure`` extra (Polars). It reuses the lint parser for block
boundaries, then reads the source lines again, because hashes need the content
of inline code that the linter replaces with a placeholder.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

from lepisma import markdown
from lepisma.engine import load_nlp

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from spacy.language import Language

# Bump when normalization or hashing changes: old and new hashes do not compare.
NORM_VERSION = 1
DEFAULT_SHINGLE_K = 5
KINDS = {"paragraph": "paragraph", "list": "list", "quote": "blockquote"}
LEMMA_POS = frozenset({"NOUN", "PROPN", "VERB", "ADJ", "NUM"})
_TOKEN = re.compile(r"\w+")

SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "repo": pl.String,
    "path": pl.String,
    "heading_path": pl.List(pl.String),
    "kind": pl.String,
    "line_start": pl.UInt32,
    "line_end": pl.UInt32,
    "text": pl.String,
    "norm_text": pl.String,
    "n_words": pl.UInt32,
    "text_hash": pl.UInt64,
    "chunk_id": pl.UInt64,
    "lemmas": pl.List(pl.String),
    "shingles": pl.List(pl.UInt64),
    "shingle_k": pl.UInt8,
    "norm_version": pl.UInt8,
}


def hash64(text: str) -> int:
    """blake2b of ``text`` as UTF-8, 8-byte digest, read as a big-endian u64."""
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def tokens(text: str) -> list[str]:
    """Normalized tokens of Markdown ``text``: markup stripped, NFKC, lowercase,
    runs of word characters."""
    plain = markdown.strip_inline(text)
    return _TOKEN.findall(unicodedata.normalize("NFKC", plain).lower())


def shingles(toks: list[str], k: int) -> list[int]:
    """Sorted distinct hashes of every ``k``-token window. Fewer than ``k``
    tokens give one hash of them all."""
    windows = [toks[i : i + k] for i in range(max(len(toks) - k, 0) + 1)]
    return sorted({hash64(" ".join(w)) for w in windows})


def chunk_id(path: str, headings: list[str], norm_text: str, occurrence: int) -> int:
    """Hash of where a chunk sits and what it says, never of its line numbers.

    Headings are normalized like the text, so emphasis or case changes in a
    heading leave the ID alone. JSON keeps the four parts apart.
    """
    norm_headings = [" ".join(tokens(h)) for h in headings]
    key = json.dumps(
        [path, norm_headings, norm_text, occurrence],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hash64(key)


@dataclass(slots=True)
class _Span:
    kind: str
    headings: list[str]
    first: int  # 1-based source lines, inclusive
    last: int
    raw: list[str]  # the lines without list markers and quote prefixes


def _spans(source: str) -> Iterator[_Span]:
    """Paragraphs, whole lists and blockquotes of one doc, with their headings."""
    lines = source.splitlines()
    stack: list[tuple[int, str]] = []
    open_list: _Span | None = None
    for block in markdown.parse(source):
        if block.kind == "heading":
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            title = " ".join(markdown.strip_inline(" ".join(block.raw)).split())
            stack.append((block.level, title))
            open_list = None
            continue
        first, last = block.starts[0][0], block.starts[-1][0]
        # Items of one list are separate blocks with only blank lines between.
        if (
            block.kind == "list"
            and open_list is not None
            and not "".join(lines[open_list.last : first - 1]).strip()
        ):
            open_list.last = last
            open_list.raw.extend(block.raw)
            continue
        span = _Span(KINDS[block.kind], [t for _, t in stack], first, last, block.raw)
        open_list = span if block.kind == "list" else None
        yield span


def chunk_docs(
    docs: Mapping[str, str],
    repo: str,
    shingle_k: int = DEFAULT_SHINGLE_K,
    nlp: Language | None = None,
) -> pl.DataFrame:
    """Chunk ``{path: markdown}`` into one row per chunk, sorted by path and line.

    ``path`` goes into the table and into ``chunk_id`` as given, so pass
    repo-relative POSIX paths.
    """
    nlp = nlp or load_nlp()
    rows: list[dict[str, object]] = []
    plain: list[str] = []
    for path, source in docs.items():
        lines = source.splitlines()
        seen: Counter[tuple[tuple[str, ...], str]] = Counter()
        # A list is complete only once the next block starts, so drain first.
        for span in list(_spans(source)):
            raw = " ".join(span.raw)
            toks = tokens(raw)
            if not toks:
                continue
            norm_text = " ".join(toks)
            key = (tuple(span.headings), norm_text)
            rows.append(
                {
                    "repo": repo,
                    "path": path,
                    "heading_path": span.headings,
                    "kind": span.kind,
                    "line_start": span.first,
                    "line_end": span.last,
                    "text": "\n".join(lines[span.first - 1 : span.last]),
                    "norm_text": norm_text,
                    "n_words": len(toks),
                    "text_hash": hash64(norm_text),
                    "chunk_id": chunk_id(path, span.headings, norm_text, seen[key]),
                    "shingles": shingles(toks, shingle_k),
                    "shingle_k": shingle_k,
                    "norm_version": NORM_VERSION,
                }
            )
            seen[key] += 1
            plain.append(" ".join(markdown.strip_inline(raw).split()))
    for row, doc in zip(rows, nlp.pipe(plain, batch_size=256), strict=True):
        row["lemmas"] = [
            t.lemma_.lower() for t in doc if t.pos_ in LEMMA_POS and not t.is_stop
        ]
    return pl.DataFrame(rows, schema=SCHEMA).sort("path", "line_start")
