import threading

from fastapi.testclient import TestClient

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
    resp = client.post("/lint", json={"files": [], "config": {"rules": {"R9": {}}}})
    assert resp.status_code == 422


def test_shutdown_sets_event():
    stop = threading.Event()
    TestClient(create_app(stop)).post(
        "/shutdown"
    )  # zorilla: ignore -- local route, not an external resource
    assert stop.is_set()
