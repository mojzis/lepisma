"""Difficulty scores and the Markdown report for a :class:`Measurement`."""

from __future__ import annotations

from typing import TYPE_CHECKING, TextIO

import polars as pl

if TYPE_CHECKING:
    from prose_lint.measure import Measurement

# Metrics that make a section or file harder when they go up. Each counts the same.
UNIT_SCORE = (
    "sentence_length_mean",
    "sentence_length_p90",
    "flesch_kincaid_grade",
    "dependency_distance_mean",
    "share_over_25",
    "nominalizations_per_100",
    "noun_verb_ratio",
    "habit_per_1k",
)
SENTENCE_SCORE = (
    "words",
    "dependency_distance",
    "main_verb_index",
    "max_noun_run",
    "passives",
    "punctuation",
)
SUMMARY = (
    "words",
    "sentence_length_mean",
    "sentence_length_median",
    "sentence_length_p90",
    "sentence_length_max",
    "share_over_25",
    "share_over_35",
    "flesch_reading_ease",
    "flesch_kincaid_grade",
    "gunning_fog",
    "lix",
    "dependency_distance_mean",
    "pos_noun",
    "pos_verb",
    "pos_adj",
    "pos_adv",
    "pos_adp",
    "noun_verb_ratio",
    "nominalizations_per_100",
    "passives_per_sentence",
    "duplicate_5gram_chr_fraction",
    "habit_per_1k",
)
TOP_UNITS = 15
TOP_SENTENCES = 30
STANDOUT_Q = 0.9
MAX_TEXT = 220


def _rank_score(df: pl.DataFrame, cols: tuple[str, ...]) -> pl.DataFrame:
    """Add ``score``: the mean percentile rank (0 to 100) of ``cols``.

    Nulls rank as the median, so a missing metric neither helps nor hurts.
    """
    n = max(df.height, 1)
    ranks = [
        ((pl.col(c).rank("average") - 1) / max(n - 1, 1)).fill_null(0.5) for c in cols
    ]
    return df.with_columns((pl.mean_horizontal(ranks) * 100).alias("score"))


def scored_units(df: pl.DataFrame, min_words: int) -> pl.DataFrame:
    """Sections or files with at least ``min_words`` words, hardest first."""
    big = df.filter(pl.col("words") >= min_words)
    return _rank_score(big, UNIT_SCORE).sort("score", descending=True)


def scored_sentences(sentences: pl.DataFrame) -> pl.DataFrame:
    """Sentences with ``score`` and ``standout`` (metrics at or above p90)."""
    df = sentences.with_columns(
        (pl.col("commas") + pl.col("parens") + pl.col("dashes")).alias("punctuation")
    )
    df = _rank_score(df, SENTENCE_SCORE)
    cuts = {c: df[c].quantile(STANDOUT_Q, "linear") for c in SENTENCE_SCORE}
    flags = [
        pl.when((pl.col(c) >= cut) & (pl.col(c) > 0))
        .then(pl.format(f"{c}={{}}", pl.col(c).round(1)))
        .otherwise(None)
        for c, cut in cuts.items()
        if cut is not None
    ]
    standout = pl.concat_list(flags).list.drop_nulls().list.join(", ")
    return df.with_columns(standout.alias("standout")).sort("score", descending=True)


def variation(files: pl.DataFrame, min_words: int) -> pl.DataFrame:
    """How much each metric spreads across files: (p90 - p10) / median."""
    big = files.filter(pl.col("words") >= min_words)
    rows = []
    for col in SUMMARY[1:]:
        s = big[col].drop_nulls()
        if s.is_empty():
            continue
        p10, med, p90 = (s.quantile(q, "linear") or 0.0 for q in (0.1, 0.5, 0.9))
        # Mostly-zero metrics (median far below p90) have no meaningful spread.
        spread = (p90 - p10) / abs(med) if abs(med) > abs(p90) / 10 else None
        rows.append(
            {"metric": col, "p10": p10, "median": med, "p90": p90, "spread": spread}
        )
    return pl.DataFrame(rows).sort("spread", descending=True, nulls_last=True)


def _fmt(v: object) -> str:
    if v is None:
        return "\u2013"
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"  # noqa: PLR2004
    return str(v)


def _table(df: pl.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = [
        "| " + " | ".join(_fmt(v).replace("|", "\\|") for v in row) + " |"
        for row in df.iter_rows()
    ]
    return "\n".join([head, sep, *body])


def _summary(m: Measurement, min_words: int) -> pl.DataFrame:
    files = m.files.filter(pl.col("words") >= min_words)
    rows = [
        {
            "metric": c,
            "median": files[c].median(),
            "p90": files[c].quantile(0.9, "linear"),
        }
        for c in SUMMARY
    ]
    rows += [
        {
            "metric": f"sentence {c}",
            "median": m.sentences[c].median(),
            "p90": m.sentences[c].quantile(0.9, "linear"),
        }
        for c in ("words", "dependency_distance", "main_verb_index", "max_noun_run")
    ]
    return pl.DataFrame(rows)


def _habit_table(m: Measurement, min_words: int) -> pl.DataFrame:
    from prose_lint.measure import habit_column  # noqa: PLC0415

    files = m.files.filter(pl.col("words") >= min_words)
    total = max(int(files["words"].sum()), 1)
    rows = []
    for w in m.habit_words:
        col = habit_column(w)
        count = round(float((files[col] * files["words"] / 1000).sum()))
        rows.append(
            {
                "word": w,
                "count": count,
                "per 1k (all docs)": count * 1000 / total,
                "files using it": int((files[col] > 0).sum()),
            }
        )
    return pl.DataFrame(rows).sort("count", descending=True)


def render(m: Measurement, min_words: int = 100) -> str:
    """The full Markdown report."""
    files = scored_units(m.files, min_words)
    sections = scored_units(m.sections, min_words)
    sents = scored_sentences(m.sentences)
    spread = variation(m.files, min_words)
    out: list[str] = []
    add = out.append

    add("# Readability report\n")
    add(
        f"{m.files.height} files, {m.sections.height} sections, "
        f"{m.sentences.height} sentences, {int(m.sentences['words'].sum()):,} words. "
        f"File and section tables only use units with at least {min_words} words "
        f"({files.height} files, {sections.height} sections); readability formulas "
        "are noise on shorter text.\n"
    )

    add("## Summary across docs\n")
    add(
        "Median and p90 across files (top block) and across all sentences "
        "(`sentence …` rows).\n"
    )
    add(_table(_summary(m, min_words)) + "\n")
    add("### Habit words\n")
    add(_table(_habit_table(m, min_words)) + "\n")

    add("## Difficulty score\n")
    add(
        "For sections and files, each of these metrics is turned into a percentile "
        "rank among the units in the table (0 = easiest, 1 = hardest), and the score "
        "is the mean rank times 100: "
        + ", ".join(f"`{c}`" for c in UNIT_SCORE)
        + ". Every metric counts the same. A score of 80 means the unit sits in the "
        "hardest fifth on average. The score is relative: it ranks these docs "
        "against each other, it is not an absolute grade.\n"
    )
    add(
        "Sentences use the same method with "
        + ", ".join(f"`{c}`" for c in SENTENCE_SCORE)
        + " (`punctuation` = commas + parentheses + dashes). `main_verb_index` "
        "is null when the root is not a verb; nulls count as the median.\n"
    )

    add(f"## Top {TOP_UNITS} hardest files\n")
    add(
        _table(
            files.head(TOP_UNITS).select(
                "path",
                pl.col("score").round(0).cast(pl.Int64),
                "words",
                "sentence_length_mean",
                "sentence_length_p90",
                "flesch_kincaid_grade",
                "dependency_distance_mean",
                "share_over_25",
                "nominalizations_per_100",
                "noun_verb_ratio",
                "habit_per_1k",
            )
        )
        + "\n"
    )

    add(f"## Top {TOP_UNITS} hardest sections\n")
    add(
        _table(
            sections.head(TOP_UNITS).select(
                pl.format("{}:{}", "path", "heading_line").alias("where"),
                pl.col("heading_path").fill_null("").str.slice(0, 60),
                pl.col("score").round(0).cast(pl.Int64),
                "words",
                "sentence_length_mean",
                "flesch_kincaid_grade",
                "share_over_25",
                "nominalizations_per_100",
            )
        )
        + "\n"
    )

    add(f"## Top {TOP_SENTENCES} hardest sentences\n")
    add(
        "`standout` lists the metrics where the sentence is in the top 10% of all "
        "sentences.\n"
    )
    for i, r in enumerate(sents.head(TOP_SENTENCES).iter_rows(named=True), 1):
        text = r["source"].replace("\n", " ")
        if len(text) > MAX_TEXT:
            text = text[: MAX_TEXT - 1] + "…"
        add(
            f"{i}. `{r['path']}:{r['line']}` score {r['score']:.0f}, "
            f"{r['words']} words — {r['standout'] or 'no single standout'}\n"
            f"   > {text}\n"
        )

    add("## Which metrics would make good linter thresholds\n")
    add(
        "`spread` is (p90 - p10) / median across files. A metric with a wide spread "
        "separates docs; one with a narrow spread is roughly the same everywhere "
        "and will not tell good docs from bad ones. A metric that is zero in most "
        "files gets no spread. Readability formulas mostly "
        "repeat sentence length and word length, so pick one of them, not all.\n"
    )
    add(_table(spread) + "\n")
    add(_threshold_note(m, spread, files))

    add("## Limits\n")
    nonzero = int((m.sections["duplicate_5gram_chr_fraction"].fill_null(0) > 0).sum())
    add(
        "- **Model.** `en_core_web_sm`. Tagging of imperative sentences "
        '("Run the tests") and of tool names is the weakest part; noun-run and '
        "main-verb numbers inherit those errors.\n"
        "- **Inline code** is replaced by the placeholder word `CODE` rather than "
        "deleted, so sentences still parse. Readability formulas count it as a short "
        "word, which flatters code-heavy prose a little.\n"
        "- **Nominalizations** use R4's definition: nouns ending in -tion, -sion, "
        "-ment, -ance, -ence or -ity, minus R4's stoplist of concrete words "
        '("function", "document").\n'
        '- **Passives** count `auxpass` tokens. Reduced passives ("the file '
        'written by X") and get-passives are missed, so these are lower bounds.\n'
        f"- **Repetition** (`duplicate_5gram_chr_fraction`, TextDescriptives) is "
        f"above zero in only {nonzero} of {m.sections.height} sections. It needs "
        "long text to say anything; use it at file level only.\n"
        "- **Sentence splitting** follows spaCy. List items and table-like lines "
        'without end punctuation can merge into one long "sentence"; check the top '
        "sentences before trusting `share_over_35`.\n"
        "- **Left out:** SMOG (needs 30+ sentences per unit, most sections are "
        "shorter) and TextDescriptives' word-level coherence metrics (need a model "
        "with word vectors).\n"
    )
    return "\n".join(out)


def _threshold_note(m: Measurement, spread: pl.DataFrame, files: pl.DataFrame) -> str:
    wide = [
        r["metric"]
        for r in spread.iter_rows(named=True)
        if r["spread"] is not None and r["metric"] != "words"
    ][:5]
    lines = ["Widest spread: " + ", ".join(f"`{c}`" for c in wide) + ".\n"]
    p90 = m.sentences["words"].quantile(0.9, "linear")
    hard = files.head(TOP_UNITS)
    if not hard.is_empty():
        lines.append(
            f"A sentence-length warning at the corpus p90 ({p90:.0f} words) would "
            f"flag 10% of sentences. The {hard.height} hardest files average "
            f"{hard['share_over_25'].mean():.0%} of sentences over 25 words, "
            f"against {files['share_over_25'].median():.0%} for the median file.\n"
        )
    return "\n".join(lines)


def print_summary(m: Measurement, min_words: int, out: TextIO) -> None:
    """A few lines for the terminal."""
    files = scored_units(m.files, min_words)
    s = m.sentences
    out.write(
        f"{m.files.height} files, {m.sections.height} sections, {s.height} sentences, "
        f"{int(s['words'].sum()):,} words\n"
        f"sentence length median {s['words'].median():.0f}, "
        f"p90 {s['words'].quantile(0.9, 'linear'):.0f}, max {s['words'].max()}; "
        f"over 25 words: {(s['words'] > 25).mean():.0%}\n"  # noqa: PLR2004
    )
    if not files.is_empty():
        out.write(
            f"Flesch-Kincaid grade median {files['flesch_kincaid_grade'].median():.1f}"
            f" across {files.height} files\nhardest files:\n"
        )
        for r in files.head(5).iter_rows(named=True):
            out.write(f"  {r['score']:5.1f}  {r['path']}\n")
