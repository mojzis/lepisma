import polars as pl
import pytest

from lepisma.chunks import chunk_docs, hash64, shingles, tokens
from lepisma.cli import main
from lepisma.config import ConfigError, from_dict

PARA = "The server keeps one model in memory and answers each request from it."

WORDS = [f"word{n}" for n in range(40)]


@pytest.fixture
def chunk(nlp):
    def run(docs: dict[str, str] | str, k: int = 5) -> list[dict]:
        if isinstance(docs, str):
            docs = {"doc.md": docs}
        return chunk_docs(docs, "demo", k, nlp).to_dicts()

    return run


def test_same_paragraph_in_two_files(chunk):
    a, b = chunk({"a.md": f"# One\n\n{PARA}\n", "b.md": f"Intro.\n\n{PARA}\n"})[0::2]
    assert (a["path"], b["path"]) == ("a.md", "b.md")
    assert a["text_hash"] == b["text_hash"]
    assert a["shingles"] == b["shingles"]
    assert a["chunk_id"] != b["chunk_id"]


@pytest.mark.parametrize(
    "variant",
    [
        PARA.replace(" model in ", " model\nin ").replace(" each ", "   each\n"),
        PARA.upper(),
        PARA.replace("one model", "**one** _model_").replace("request", "*request*"),
        PARA.replace("server", "[server](https://example.com/s)"),
    ],
    ids=["rewrapped", "uppercase", "emphasis", "link"],
)
def test_reflow_case_and_markup_keep_every_hash(chunk, variant):
    (plain,) = chunk(PARA)
    (changed,) = chunk(variant)
    for column in ("norm_text", "text_hash", "chunk_id", "shingles"):
        assert changed[column] == plain[column], column


def test_inline_code_keeps_its_content(chunk):
    (row,) = chunk("Run `uv sync` first.")
    assert row["norm_text"] == "run uv sync first"
    assert row["text"] == "Run `uv sync` first."


def test_paragraph_above_leaves_chunk_id(chunk):
    (before,) = chunk(f"# Top\n\n{PARA}\n")
    after = chunk(f"# Top\n\nA new paragraph.\n\n{PARA}\n")[1]
    assert after["chunk_id"] == before["chunk_id"]
    assert (before["line_start"], after["line_start"]) == (3, 5)


def test_one_changed_word_keeps_most_shingles(chunk):
    edited = [*WORDS[:20], "changed", *WORDS[21:]]
    (a,) = chunk(" ".join(WORDS))
    (b,) = chunk(" ".join(edited))
    assert a["text_hash"] != b["text_hash"]
    assert len(a["shingles"]) == 36
    # One word sits in 5 of the 36 windows.
    assert len(set(a["shingles"]) & set(b["shingles"])) == 31


def test_code_tables_and_front_matter_give_no_rows(chunk):
    doc = (
        "---\ntitle: x\n---\n\n# Heading only\n\n```python\nprint('fenced code')\n```\n"
        "\n    indented code\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n"
        "<!-- a comment\nover two lines -->\n"
    )
    assert chunk(doc) == []


STRUCTURE = (
    "# Guide\n\nIntro text\nover two lines.\n\n## Set *up*\n\n"
    "- first item\n  wrapped\n- second item\n\n- third, after a blank\n\n"
    "> quoted\n> words\n\n```\ncode\n```\n\n1. another list\n\n# Other\n\nLast.\n"
)


def test_kinds_and_line_ranges(chunk):
    # A list runs over blank lines between items, but not over a code block.
    rows = chunk(STRUCTURE)
    assert [(r["kind"], r["line_start"], r["line_end"]) for r in rows] == [
        ("paragraph", 3, 4),
        ("list", 8, 12),
        ("blockquote", 14, 15),
        ("list", 21, 21),
        ("paragraph", 25, 25),
    ]


def test_heading_path_follows_levels(chunk):
    assert [r["heading_path"] for r in chunk(STRUCTURE)] == [
        ["Guide"],
        ["Guide", "Set up"],
        ["Guide", "Set up"],
        ["Guide", "Set up"],
        ["Other"],
    ]


def test_whole_list_is_one_chunk(chunk):
    whole = chunk(STRUCTURE)[1]
    assert (whole["text"], whole["norm_text"], whole["n_words"]) == (
        "\n".join(STRUCTURE.splitlines()[7:12]),
        "first item wrapped second item third after a blank",
        9,
    )


def test_twins_under_one_heading_get_distinct_ids(chunk):
    first, second = chunk(f"# Top\n\n{PARA}\n\n{PARA}\n")
    assert first["text_hash"] == second["text_hash"]
    assert first["chunk_id"] != second["chunk_id"]


def test_short_chunk_gets_one_shingle(chunk):
    (row,) = chunk("Only three words.")
    assert row["shingles"] == [row["text_hash"]]
    assert shingles(["a", "b"], 5) == [hash64("a b")]


def test_shingle_k_changes_shingles_only(chunk):
    (five,) = chunk(PARA)
    (three,) = chunk(PARA, k=3)
    assert (five["shingle_k"], three["shingle_k"]) == (5, 3)
    assert len(three["shingles"]) == len(five["shingles"]) + 2
    assert three["text_hash"] == five["text_hash"]


def test_lemmas_keep_content_words_in_order(chunk):
    (row,) = chunk("The two servers were quickly parsing the big files and the files.")
    assert row["lemmas"] == ["server", "parse", "big", "file", "file"]


def test_tokens_fold_width_and_case():
    # NFKC folds the full-width letters and the ligature.
    assert tokens("\uff21\uff22\uff23 \ufb01le Über-cool, snake_case!") == [
        "abc",
        "file",
        "über",
        "cool",
        "snake_case",
    ]


def test_golden_hashes(chunk):
    # Pins normalization and hashing. A change here needs a NORM_VERSION bump.
    (row,) = chunk("# Head\n\nThe **quick** brown fox\njumps over the `lazy` dog.\n")
    pinned = ("norm_text", "text_hash", "chunk_id", "shingles", "shingle_k")
    assert {c: row[c] for c in (*pinned, "norm_version")} == {
        "norm_text": "the quick brown fox jumps over the lazy dog",
        # Same as `printf '%s' "$norm_text" | b2sum -l 64`, read as hex.
        "text_hash": 0x2BB50820DEFDFBF2,
        "chunk_id": 4715741251154127231,
        "shingles": [
            4800378933827958851,
            6573469244424666089,
            11033456989573087361,
            14029935466038595319,
            14540364934603910825,
        ],
        "shingle_k": 5,
        "norm_version": 1,
    }


def test_rows_sorted_by_path_and_line(nlp):
    table = chunk_docs({"b.md": "Two.\n\nThree.\n", "a.md": "One.\n"}, "demo", nlp=nlp)
    assert table.select("path", "line_start").rows() == [
        ("a.md", 1),
        ("b.md", 1),
        ("b.md", 3),
    ]


def test_table_has_the_documented_types(nlp):
    table = chunk_docs({"a.md": "One.\n"}, "demo", nlp=nlp)
    assert dict(table.schema) == {
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


@pytest.fixture
def docs_dir(tmp_path, monkeypatch):
    """A folder with one doc to chunk, one ignored and one hidden."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lepisma.toml").write_text(
        'ignore = ["skip/*"]\n[chunks]\nshingle_k = 3\n'
    )
    for folder in ("docs", "skip", ".hidden"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "a.md").write_text(f"{PARA}\n")
    return tmp_path


def test_cli_defaults_to_the_root_and_its_name(docs_dir, capsys):
    assert main(["chunks", "--out", "out/chunks.parquet"]) == 0
    table = pl.read_parquet(docs_dir / "out" / "chunks.parquet")
    assert table.select("repo", "path", "shingle_k").rows() == [
        (docs_dir.name, "docs/a.md", 3)
    ]
    assert "1 chunks from 1 docs" in capsys.readouterr().out


def test_cli_repo_and_no_ignore(docs_dir):
    main(["chunks", ".", "--repo", "named", "--no-ignore", "--out", "c.parquet"])
    assert pl.read_parquet("c.parquet").select("repo", "path").rows() == [
        ("named", "docs/a.md"),
        ("named", "skip/a.md"),
    ]


def test_cli_output_is_byte_identical(docs_dir):
    main(["chunks", "--out", "one.parquet"])
    main(["chunks", "--out", "two.parquet"])
    assert (docs_dir / "one.parquet").read_bytes() == (
        docs_dir / "two.parquet"
    ).read_bytes()


def test_cli_no_docs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["chunks"]) == 1


def test_shingle_k_is_a_config_key():
    assert from_dict({"chunks": {"shingle_k": 7}}).chunks.shingle_k == 7


@pytest.mark.parametrize("bad", [0, 256])
def test_shingle_k_must_fit_one_byte(bad):
    with pytest.raises(ConfigError, match="shingle_k"):
        from_dict({"chunks": {"shingle_k": bad}})
