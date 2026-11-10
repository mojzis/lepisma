"""Readability statistics for whole Markdown docs, as Polars tables.

Usable as a library, for example from a docs server::

    from lepisma.measure import Measurer

    measurer = Measurer()                      # loads spaCy once
    result = measurer.measure({"guide.md": text})
    result.files.row(0, named=True)            # one dict of file metrics
    result.sentences.sort("words", descending=True).head(5)

Needs the ``measure`` extra (TextDescriptives and Polars). It reuses the lint
parser and the R2 to R4 helpers, so the numbers match what the linter warns on.
"""

from __future__ import annotations

import re
import warnings
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from spacy.tokens import Doc

from lepisma import markdown
from lepisma.config import Config
from lepisma.engine import load_nlp, parse_blocks
from lepisma.rules import habit_hits, is_nominal, is_word, noun_count, noun_runs

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from spacy.language import Language
    from spacy.tokens import Span

    from lepisma.markdown import Block

MIN_LIST_WORDS = 4  # list items shorter than this are fragments, not sentences
LONG = 25
VERY_LONG = 35
POS_TAGS = ("NOUN", "VERB", "ADJ", "ADV", "ADP")
READABILITY = ("flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog", "lix")
_DASH = re.compile("\u2014|\\s--\\s|\\s\u2013\\s")  # em dash, --, spaced en dash


def habit_column(word: str) -> str:
    """Column name for one habit word, e.g. ``habit_in_order_to``."""
    return "habit_" + re.sub(r"\W+", "_", word.lower()).strip("_")


@dataclass(slots=True)
class _Section:
    path: str
    index: int
    heading_path: str
    heading_line: int
    lines: list[str]
    blocks: list[tuple[Block, Doc]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Measurement:
    """Metrics per sentence, per section and per file."""

    sentences: pl.DataFrame
    sections: pl.DataFrame
    files: pl.DataFrame
    habit_words: tuple[str, ...]

    def write(self, out_dir: Path) -> None:
        """Write ``sentences``, ``sections`` and ``files`` as Parquet."""
        out_dir.mkdir(parents=True, exist_ok=True)
        self.sentences.write_parquet(out_dir / "sentences.parquet")
        self.sections.write_parquet(out_dir / "sections.parquet")
        self.files.write_parquet(out_dir / "files.parquet")


def _td_components(nlp: Language) -> list[Callable[[Doc], Doc]]:
    """TextDescriptives components, called directly on combined docs."""
    from textdescriptives.components.quality import Quality  # noqa: PLC0415

    names = ("readability", "dependency_distance", "pos_proportions")
    comps = [nlp.create_pipe(f"textdescriptives/{n}") for n in names]
    # The quality factory fails confection's config check (lists vs tuples) in
    # textdescriptives 2.8.4, so build the component by hand with its defaults.
    comps.append(Quality(nlp, "textdescriptives/quality", (2, 4), 3, (5, 10), None))
    return comps


class Measurer:
    """Holds the loaded model. Reuse one instance across calls."""

    def __init__(self, cfg: Config | None = None, nlp: Language | None = None):
        self.cfg = cfg or Config()
        self.nlp = nlp or load_nlp()
        self.habit_words = tuple(self.cfg.habit_words.words)
        self._td = _td_components(self.nlp)
        self._dep_distance = self._td[1]

    def measure(self, docs: Mapping[str, str]) -> Measurement:
        """Measure ``{path: markdown}``."""
        sections = self._sections(docs)
        sentence_rows = [
            row
            for sec in sections
            for block, doc in sec.blocks
            for row in self._sentence_rows(sec, block, doc)
        ]
        sentences = pl.DataFrame(sentence_rows, schema=self._sentence_schema())
        sec_td = [
            {"path": s.path, "section": s.index, **self._doc_metrics(s.blocks)}
            for s in sections
            if s.blocks
        ]
        by_file: dict[str, list[tuple[Block, Doc]]] = {}
        for s in sections:
            by_file.setdefault(s.path, []).extend(s.blocks)
        file_td = [{"path": p, **self._doc_metrics(b)} for p, b in by_file.items() if b]
        heads = pl.DataFrame(
            [
                {
                    "path": s.path,
                    "section": s.index,
                    "heading_path": s.heading_path,
                    "heading_line": s.heading_line,
                }
                for s in sections
                if s.blocks
            ],
            schema={
                "path": pl.String,
                "section": pl.Int64,
                "heading_path": pl.String,
                "heading_line": pl.Int64,
            },
        )
        sec_keys = ["path", "section"]
        section_df = heads.join(
            self._aggregate(sentences, sec_keys), on=sec_keys, how="inner"
        ).join(_frame(sec_td, sec_keys), on=sec_keys, how="left")
        file_df = self._aggregate(sentences, ["path"]).join(
            _frame(file_td, ["path"]), on="path", how="left"
        )
        return Measurement(
            sentences=sentences,
            sections=_finish(section_df),
            files=_finish(file_df),
            habit_words=self.habit_words,
        )

    def measure_paths(self, files: Iterable[Path]) -> Measurement:
        """Measure files read from disk."""
        return self.measure({str(f): f.read_text(encoding="utf-8") for f in files})

    # -- parsing ----------------------------------------------------------------

    def _keep(self, block: Block) -> bool:
        if block.kind == "heading" or block.is_identifier_list_item():
            return False
        if block.kind == "list":
            return len(block.text.split()) >= MIN_LIST_WORDS
        return True

    def _sections(self, docs: Mapping[str, str]) -> list[_Section]:
        """Split each doc into sections by heading and parse all prose at once."""
        sections: list[_Section] = []
        pending: list[tuple[_Section, Block]] = []
        for path, text in docs.items():
            stack: list[tuple[int, str]] = []
            lines = text.splitlines()
            sec = _Section(path, 0, "", 1, lines)
            sections.append(sec)
            for block in markdown.parse(text):
                if block.kind == "heading":
                    while stack and stack[-1][0] >= block.level:
                        stack.pop()
                    title = " ".join(block.raw).replace("`", "").strip()
                    stack.append((block.level, title))
                    sec = _Section(
                        path,
                        sec.index + 1,
                        " > ".join(t for _, t in stack),
                        block.position(0)[0],
                        lines,
                    )
                    sections.append(sec)
                elif self._keep(block):
                    pending.append((sec, block))
        parsed = parse_blocks(self.nlp, (b for _, b in pending), batch_size=256)
        for (sec, block), doc in zip(pending, parsed, strict=True):
            sec.blocks.append((block, self._dep_distance(doc)))
        return sections

    # -- per sentence ------------------------------------------------------------

    def _sentence_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "path": pl.String,
            "section": pl.Int64,
            "line": pl.Int64,
            "col": pl.Int64,
            "text": pl.String,
            "source": pl.String,
            "words": pl.Int64,
            "dependency_distance": pl.Float64,
            "main_verb_index": pl.Int64,
            "max_noun_run": pl.Int64,
            "passives": pl.Int64,
            "commas": pl.Int64,
            "parens": pl.Int64,
            "dashes": pl.Int64,
            "nominalizations": pl.Int64,
            "habit_total": pl.Int64,
        }
        schema.update(dict.fromkeys(map(habit_column, self.habit_words), pl.Int64))
        return schema

    def _sentence_rows(
        self, sec: _Section, block: Block, doc: Doc
    ) -> Iterable[dict[str, Any]]:
        hits = habit_hits(block, doc, self.cfg)
        for sent in doc.sents:
            words = [t for t in sent if is_word(t)]
            if all(block.in_code(t.idx, t.idx + len(t)) for t in words):
                continue  # empty, or only inline code like "`--out`"
            first = words[0]
            line, col = block.position(first.idx)
            text = sent.text.strip()
            in_sent = Counter(
                w for off, w in hits if sent.start_char <= off < sent.end_char
            )
            dd = sent._.dependency_distance or {}
            yield {
                "path": sec.path,
                "section": sec.index,
                "line": line,
                "col": col,
                "text": text,
                "source": _source(sec.lines, block, first.idx, words[-1]),
                "words": len(words),
                "dependency_distance": dd.get("dependency_distance_mean"),
                "main_verb_index": _main_verb_index(sent, words),
                "max_noun_run": _max_noun_run(block, sent),
                "passives": sum(1 for t in sent if t.dep_ == "auxpass"),
                "commas": text.count(","),
                "parens": text.count("("),
                "dashes": len(_DASH.findall(text)),
                "nominalizations": sum(1 for t in sent if is_nominal(t, self.cfg)),
                "habit_total": sum(in_sent.values()),
                **{habit_column(w): in_sent[w] for w in self.habit_words},
            }

    # -- per section / file ------------------------------------------------------

    def _doc_metrics(self, blocks: list[tuple[Block, Doc]]) -> dict[str, Any]:
        """TextDescriptives metrics for blocks joined into one doc."""
        doc = Doc.from_docs([d for _, d in blocks])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for comp in self._td:
                doc = comp(doc)
        read = doc._.readability
        pos = doc._.pos_proportions
        quality = doc._.quality
        noun, verb = pos.get("pos_prop_NOUN", 0.0), pos.get("pos_prop_VERB", 0.0)
        return {
            **{k: read.get(k) for k in READABILITY},
            "dependency_distance_mean": doc._.dependency_distance[
                "dependency_distance_mean"
            ],
            **{f"pos_{t.lower()}": pos.get(f"pos_prop_{t}", 0.0) for t in POS_TAGS},
            "noun_verb_ratio": noun / verb if verb else None,
            "duplicate_5gram_chr_fraction": quality.duplicate_ngram_chr_fraction[
                "5"
            ].value,
        }

    def _aggregate(self, sentences: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
        habit_cols = [habit_column(w) for w in self.habit_words]
        words = pl.col("words")
        return sentences.group_by(keys, maintain_order=True).agg(
            pl.len().alias("sentences"),
            words.sum().alias("words"),
            words.mean().alias("sentence_length_mean"),
            words.median().alias("sentence_length_median"),
            words.quantile(0.9, "linear").alias("sentence_length_p90"),
            words.max().alias("sentence_length_max"),
            (words > LONG).mean().alias("share_over_25"),
            (words > VERY_LONG).mean().alias("share_over_35"),
            pl.col("passives").mean().alias("passives_per_sentence"),
            pl.col("max_noun_run").max().alias("max_noun_run"),
            (pl.col("nominalizations").sum() * 100 / words.sum()).alias(
                "nominalizations_per_100"
            ),
            (pl.col("habit_total").sum() * 1000 / words.sum()).alias("habit_per_1k"),
            *[(pl.col(c).sum() * 1000 / words.sum()).alias(c) for c in habit_cols],
        )


def _main_verb_index(sent: Span, words: list[Any]) -> int | None:
    """1-based word index of the root when the root is a verb."""
    root = sent.root
    if root.pos_ not in {"VERB", "AUX"}:
        return None
    for n, tok in enumerate(words, start=1):
        if tok.i == root.i:
            return n
    return None


def _max_noun_run(block: Block, sent: Span) -> int:
    """Longest run of nouns or proper nouns; "ty-find" counts as one."""
    return max((noun_count(run) for run in noun_runs(block, sent)), default=0)


_CODE_END = re.compile(r"(`+).*?\1|<[^>]*>|\S+")


def _source(lines: list[str], block: Block, start: int, last: Any) -> str:
    """The sentence as written in the Markdown file, from its first word to the
    end of its last token, with inline code and links intact."""
    tok = last
    # Keep closing punctuation glued to the last word, like ")." or "!".
    while not tok.whitespace_ and tok.i + 1 < len(tok.doc) and tok.nbor(1).is_punct:
        tok = tok.nbor(1)
    end_char = tok.idx + len(tok) - 1
    (l1, c1), (l2, c2) = block.position(start), block.position(end_char)
    stop = c2
    if block.in_code(end_char, end_char + 1):
        m = _CODE_END.match(lines[l2 - 1], c2 - 1)
        stop = m.end() if m else c2
    if l1 == l2:
        return lines[l1 - 1][c1 - 1 : stop]
    parts = [lines[l1 - 1][c1 - 1 :], *lines[l1 : l2 - 1], lines[l2 - 1][:stop]]
    return " ".join(p.strip() for p in parts)


def _frame(rows: list[dict[str, Any]], keys: list[str]) -> pl.DataFrame:
    if rows:
        return pl.DataFrame(rows)
    return pl.DataFrame(schema=dict.fromkeys(keys, pl.String))


def _finish(df: pl.DataFrame) -> pl.DataFrame:
    return df.sort(df.columns[: 2 if "section" in df.columns else 1])
