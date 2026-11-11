import pytest

from lepisma.measure import Measurer

DOC = """# Shape, not size

The cache \\u2014 a plain dict \\u2014 holds parsed files (one per path); nothing else.

The hook is an inventory, not a verdict. It isn't a gate. It's a report.

- `name` \\u2014 the symbol to look for
- Note: this one has a label colon and enough words.

We chose the slow path rather than the fast one because the fast path loses data.
It exactly matches.

The server returns the parsed tree, making the next call cheap.

The parser wants a file -> it reads the all-in-one config. Falls back to the path.

The **daemon** speaks LSP and **never** MCP (Model Context Protocol).
"""


@pytest.fixture(scope="module")
def measured(nlp):
    doc = DOC.encode().decode("unicode_escape")
    return Measurer(nlp=nlp).measure({"doc.md": doc})


@pytest.fixture(scope="module")
def by_line(measured):
    rows: dict[int, dict[str, int]] = {}
    for r in measured.sentences.iter_rows(named=True):
        totals = rows.setdefault(r["line"], {})
        for key, value in r.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return rows


def test_interrupters_count_marks_in_one_sentence(by_line):
    row = by_line[3]
    assert (row["em_dashes"], row["parentheticals"], row["semicolons"]) == (2, 1, 1)
    assert row["interrupters"] == 4


def test_label_dash_and_label_colon_do_not_interrupt(by_line):
    assert by_line[7]["interrupters"] == 0
    assert by_line[8]["interrupters"] == 0


def test_contrast_frames_within_and_across_sentences(by_line):
    # "X, not Y" plus "isn't X. It's Y".
    assert by_line[5]["contrast_frames"] == 2
    assert by_line[10]["contrast_frames"] == 1  # rather than


def test_heading_contrast_counts_at_file_level(measured):
    assert measured.files.row(0, named=True)["heading_contrast_frames"] == 1


def test_emphasis_families(by_line):
    assert by_line[5]["figurative"] == 1  # verdict
    assert by_line[11]["sincerity"] == 1  # exactly
    assert by_line[17]["block_bold_spans"] == 2


def test_punchline_follows_a_long_sentence(by_line):
    assert by_line[11]["punchline"] == 1
    assert by_line[5]["punchline"] == 0


def test_trailing_participle(by_line):
    assert by_line[13]["trailing_participle"] == 1


def test_compression_and_inanimate_actor(by_line):
    row = by_line[15]
    assert (row["arrows"], row["hyphen_compounds"]) == (1, 1)
    assert row["inanimate_actor"] == 1


def test_unexpanded_acronyms(measured):
    row = measured.files.row(0, named=True)
    # MCP is spelled out next to its first use; LSP never is.
    assert row["acronym_list"] == "LSP"
    assert row["acronyms_unexpanded"] == 1


def test_file_rates(measured):
    row = measured.files.row(0, named=True)
    assert row["em_dashes_per_1k"] > 0
    assert 0 < row["share_interrupted"] < 1
