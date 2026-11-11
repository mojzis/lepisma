from lepisma.markdown import ALL_RULES, PLACEHOLDER, parse


def texts(source: str) -> list[str]:
    return [b.text for b in parse(source)]


def test_fenced_code_and_tables_are_dropped():
    source = """Intro line.

```python
utilize = leverage()
```

| a | b |
|---|---|
| utilize | x |

Outro line.
"""
    assert texts(source) == ["Intro line.", "Outro line."]


def test_front_matter_is_skipped():
    assert texts("---\ntitle: Robust\n---\nBody.\n") == ["Body."]


def test_inline_code_becomes_placeholder_and_links_keep_text():
    (block,) = parse("Run `make all` then read [the guide](https://x.io/a).\n")
    assert block.text == f"Run {PLACEHOLDER} then read the guide."
    start = block.text.index(PLACEHOLDER)
    assert block.in_code(start, start + 1)


def test_positions_map_back_to_source():
    (block,) = parse("First line\n  second **bold** word\n")
    offset = block.text.index("word")
    assert block.position(offset) == (2, 19)


def test_paragraph_lines_join_and_list_items_split():
    blocks = parse("One\ntwo.\n\n- item a\n- item b\n")
    assert [(b.kind, b.text) for b in blocks] == [
        ("paragraph", "One two."),
        ("list", "item a"),
        ("list", "item b"),
    ]


def test_identifier_list_items_are_recognised():
    blocks = parse("- `max_retries`\n- user_id\n- Retry the request twice.\n")
    assert [b.is_identifier_list_item() for b in blocks] == [True, True, False]


def test_headings_including_setext():
    blocks = parse("# Title\n\nSub\n---\n\nText.\n")
    assert [(b.kind, b.text) for b in blocks] == [
        ("heading", "Title"),
        ("heading", "Sub"),
        ("paragraph", "Text."),
    ]


def test_disable_enable_and_disable_next():
    source = """<!-- lepisma: disable R2 noun-stack -->
A.

<!-- lepisma: enable R2 -->
<!-- lepisma: disable-next -->
B.

C.
"""
    disabled = [sorted(b.disabled) for b in parse(source)]
    assert disabled == [["R2"], sorted(ALL_RULES), []]


def test_multiline_html_comment_is_skipped():
    assert texts("<!--\nrobust notes\n-->\nText.\n") == ["Text."]


def breaks_at(source: str) -> list[str]:
    """Text of each forced sentence start in a single-block ``source``."""
    (block,) = parse(source)
    return [block.text[b : b + 6] for b in block.breaks]


def test_marker_and_bold_label_lines_start_new_items():
    assert breaks_at("✅ One item\n✅ Two item\n⚠️ Three item\n") == ["✅ Two ", "⚠️ Thr"]
    assert breaks_at("**Status:** Draft\n**Owner**: Platform Team\n") == ["Owner:"]


def test_plain_label_breaks_only_after_another_item_line():
    assert breaks_at("Search: shows by name\nLimit: basic metadata\n") == ["Limit:"]
    assert breaks_at("Never put it in a hook or\nCI: it runs the suite.\n") == []


def test_wrapped_prose_does_not_break():
    source = (
        "The tool reads the\n`config` file, the [guide](x.md) and\nPython sources\n"
    )
    assert breaks_at(source) == []
    assert breaks_at("A shortcut in the\n⌘-tab switcher and an arrow\n→ here\n") == []


def test_inline_code_wrapped_over_two_lines_is_one_placeholder():
    src = "Run with `GIT_DIR` and the rest of `git\nrev-parse --local-env-vars` set.\n"
    (block,) = parse(src)
    assert block.text == "Run with CODE and the rest of CODE set."
    assert block.position(block.text.index("set")) == (2, 29)
    assert block.in_code(27, 31)


def test_link_wrapped_over_two_lines_drops_its_target():
    src = "A [fallback\ncommand](commands/run.md#the-fallback-command) inherits.\n"
    (block,) = parse(src)
    assert block.text == "A fallback command inherits."
    assert block.position(block.text.index("command")) == (2, 1)


def test_wrapped_code_span_does_not_start_an_item():
    src = "**Status:** see `a\n**b:** c` now\n**Owner:** me\n"
    (block,) = parse(src)
    assert block.text == "Status: see CODE now Owner: me"
    assert block.breaks == [block.text.index("Owner")]
