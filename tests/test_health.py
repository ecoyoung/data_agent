import pytest


fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")


def test_health_check() -> None:
    from fastapi.testclient import TestClient

    from data_agent.main import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "shu-tan"}
