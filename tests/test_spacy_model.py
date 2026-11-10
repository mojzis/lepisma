import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from prose_lint import cli, spacy_model
from prose_lint.spacy_model import MODEL, VERSION, ModelError, locate


def _fake_wheel() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{MODEL}/{MODEL}-{VERSION}/config.cfg", "[nlp]\n")
    return buf.getvalue()


@pytest.fixture
def no_model(monkeypatch, tmp_path):
    """The model package is absent and the cache is empty; fetches are recorded."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv(spacy_model.WHEEL_ENV, raising=False)
    monkeypatch.setattr(spacy_model.importlib.util, "find_spec", lambda _name: None)
    wheel = _fake_wheel()
    monkeypatch.setattr(spacy_model, "WHEEL_SHA256", hashlib.sha256(wheel).hexdigest())
    fetched: list[str] = []

    def fetch(source: str) -> bytes:
        fetched.append(source)
        return wheel

    monkeypatch.setattr(spacy_model, "_fetch", fetch)
    return fetched


def test_installed_package_is_loaded_by_name(monkeypatch):
    monkeypatch.setattr(spacy_model.importlib.util, "find_spec", lambda _name: object())
    assert locate() == MODEL


def test_missing_model_is_unpacked_into_the_user_cache(no_model, tmp_path):
    path = locate()
    assert isinstance(path, Path)
    assert (path / "config.cfg").is_file()
    assert path.is_relative_to(tmp_path / "prose-lint" / "models")


def test_missing_model_downloads_once_with_notice(no_model, capsys):
    assert locate() == locate()
    assert no_model == [spacy_model.WHEEL_URL]
    assert capsys.readouterr().err.count("downloading spaCy model") == 1


def test_env_var_overrides_source(no_model, monkeypatch, tmp_path):
    local = str(tmp_path / "model.whl")
    monkeypatch.setenv(spacy_model.WHEEL_ENV, local)
    locate()
    assert no_model == [local]


def test_hash_mismatch_leaves_no_model(no_model, monkeypatch, tmp_path):
    monkeypatch.setattr(spacy_model, "WHEEL_SHA256", "0" * 64)
    with pytest.raises(ModelError, match="SHA-256"):
        locate()
    assert not (tmp_path / "prose-lint" / "models").exists()


def test_fetch_failure_explains_offline_install(no_model, monkeypatch):
    def offline(_source: str) -> bytes:
        raise OSError("network unreachable")

    monkeypatch.setattr(spacy_model, "_fetch", offline)
    with pytest.raises(ModelError, match="uv pip install"):
        locate()


def test_cli_reports_model_error_and_exits_2(monkeypatch, capsys):
    def fail(_args):
        raise ModelError("could not fetch")

    monkeypatch.setattr(cli, "cmd_check", fail)
    assert cli.main(["check", "x.md"]) == 2
    assert capsys.readouterr().err == "prose-lint: could not fetch\n"
