import threading

from fastapi.testclient import TestClient

from lepisma.config import load_raw
from lepisma.server import BUILD, create_app


def test_health_reports_version():
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok", "version": BUILD}


def test_lint_returns_results_and_uses_config():
    client = TestClient(create_app())
    payload = {
        "files": [{"path": "a.md", "text": "We leverage it.\n"}],
        "config": {"rules": {"R3": {"enabled": True}}},
    }
    first = client.post("/lint", json=payload).json()
    second = client.post("/lint", json=payload).json()  # served from cache
    assert first == second
    (result,) = first["results"]
    assert result["path"] == "a.md"
    assert [w["rule"] for w in result["warnings"]] == ["R3"]


def test_bad_config_is_422():
    client = TestClient(create_app())
    resp = client.post("/lint", json={"files": [], "config": {"rules": {"R99": {}}}})
    assert resp.status_code == 422


def test_shutdown_sets_event():
    stop = threading.Event()
    TestClient(create_app(stop)).post(
        "/shutdown"
    )  # zorilla: ignore -- local route, not an external resource
    assert stop.is_set()


def test_editing_a_glossary_changes_the_result_for_unchanged_text(tmp_path):
    client = TestClient(create_app())
    (tmp_path / "lepisma.toml").write_text('[rules.R10]\nglossary = ["g.toml"]\n')
    glossary = tmp_path / "g.toml"

    def warnings():
        payload = {
            "files": [{"path": "a.md", "text": "Each ADR names one choice.\n"}],
            "config": load_raw(tmp_path),  # what the hook client posts
        }
        (result,) = client.post("/lint", json=payload).json()["results"]
        return [w["rule"] for w in result["warnings"]]

    glossary.write_text('[LSP]\nexpansion = "Language Server Protocol"\n')
    assert warnings() == ["R10"]
    glossary.write_text('[ADR]\nexpansion = "Architecture Decision Record"\n')
    assert warnings() == []
