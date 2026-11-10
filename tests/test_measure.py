import io

import polars as pl
import pytest

from prose_lint.cli import main
from prose_lint.measure import Measurer, habit_column
from prose_lint.measure_report import print_summary, render, scored_sentences

DOC = """---
title: x
---
# Guide

Run `uv sync` first. The config file is validated by the server before startup.

## Setup

- `max_retries`
- a short item
- This list item has enough words to count as a sentence.

We leverage the database connection pool configuration value in order to scale.

```
code is ignored here
```
"""


@pytest.fixture(scope="module")
def measured(nlp):
    return Measurer(nlp=nlp).measure({"doc.md": DOC})


@pytest.fixture(scope="module")
def by_pos(measured):
    return {(r["line"], r["col"]): r for r in measured.sentences.iter_rows(named=True)}


def test_sentences_trace_back_to_source(by_pos):
    # Headings, code, front matter and short list items are not sentences.
    assert sorted(by_pos) == [(6, 1), (6, 22), (12, 3), (14, 1)]
    assert by_pos[6, 1]["source"] == "Run `uv sync` first."
    assert by_pos[6, 1]["text"] == "Run CODE first."


def test_habit_words_and_noun_run(by_pos):
    leverage = by_pos[14, 1]
    assert leverage["max_noun_run"] >= 4
    assert leverage[habit_column("leverage")] == 1
    assert leverage[habit_column("in order to")] == 1
    assert leverage["habit_total"] == 2


def test_passive_counted(measured):
    row = measured.sentences.filter(pl.col("text").str.contains("validated")).row(
        0, named=True
    )
    assert row["passives"] == 1
    assert row["main_verb_index"] == 5


def test_sections_carry_heading_path(measured):
    paths = measured.sections["heading_path"].to_list()
    assert paths == ["Guide", "Guide > Setup"]
    assert measured.sections["sentences"].to_list() == [2, 2]


def test_files_have_readability(measured):
    row = measured.files.row(0, named=True)
    assert row["sentences"] == 4
    assert row["flesch_kincaid_grade"] is not None
    assert 0 < row["pos_noun"] < 1


def test_report_and_summary(measured):
    report = render(measured, min_words=1)
    for heading in ("## Summary across docs", "## Difficulty score", "## Limits"):
        assert heading in report
    assert "`doc.md:14`" in report
    out = io.StringIO()
    print_summary(measured, 1, out)
    assert "4 sentences" in out.getvalue()


def test_sentence_scores_flag_standouts(measured):
    top = scored_sentences(measured.sentences).row(0, named=True)
    assert top["line"] == 14
    assert "max_noun_run" in top["standout"]


def test_cli_writes_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(DOC)
    assert main(["measure", "docs", "--out", "out", "--min-words", "1"]) == 0
    for name in ("sentences.parquet", "sections.parquet", "files.parquet"):
        assert (tmp_path / "out" / name).exists()
    assert (tmp_path / "out" / "report.md").read_text().startswith("# Readability")
    assert "hardest files" in capsys.readouterr().out


def test_cli_no_docs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["measure", "."]) == 1
