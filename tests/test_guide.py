import re
import tomllib

import pytest

from prose_lint.cli import main
from prose_lint.config import from_dict
from prose_lint.guide import TOPICS, render


@pytest.mark.parametrize("topic", list(TOPICS))
def test_topic_prints_and_exits_zero(topic, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["guide", topic]) == 0
    out = capsys.readouterr()
    assert out.out.startswith(f"# prose-lint guide: {topic}\n")
    assert out.err == ""
    assert "\nnext: `" in out.out


@pytest.mark.parametrize("topic", list(TOPICS))
def test_page_fills_placeholders_and_names_real_commands(topic, capsys):
    page = render(topic)
    assert "{{" not in page
    code = " ".join(re.findall(r"```.*?```|`[^`\n]+`", page, re.DOTALL))
    used = set(re.findall(r"prose-lint ([a-z][a-z-]*)", code))
    assert used
    for command in used:
        with pytest.raises(SystemExit) as exit_info:
            main([command, "--help"])
        assert exit_info.value.code == 0, command
    capsys.readouterr()


def test_tune_toml_block_is_a_valid_config():
    block = render("tune").split("```toml\n", 1)[1].split("```", 1)[0]
    cfg = from_dict(tomllib.loads(block))
    assert cfg.long_sentence.max_words == 25


def test_auto_picks_setup_in_empty_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["guide"]) == 0
    assert capsys.readouterr().out.splitlines()[0].endswith("-> setup")


def test_auto_picks_triage_with_config_above(tmp_path, monkeypatch, capsys):
    (tmp_path / "prose-lint.toml").write_text("")
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path / "docs")
    assert main(["guide"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert "prose-lint.toml" in first
    assert first.endswith("-> triage")


def test_auto_picks_triage_with_madoqua_step(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.madoqua]\nextend_check = [{ name = "p", cmd = "prose-lint hook" }]\n'
    )
    monkeypatch.chdir(tmp_path)
    assert main(["guide"]) == 0
    assert capsys.readouterr().out.splitlines()[0].endswith("-> triage")


def test_unwritable_stdout_exits_one(monkeypatch):
    class Closed:
        def write(self, _text):
            raise BrokenPipeError

    monkeypatch.setattr("sys.stdout", Closed())
    assert main(["guide", "tune"]) == 1
