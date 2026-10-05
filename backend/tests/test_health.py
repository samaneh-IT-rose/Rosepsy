from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok_envelope():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ok"
    assert body["errors"] is None
    assert body["meta"]["request_id"]


def test_request_id_header_present():
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_request_id_is_propagated():
    response = client.get("/health", headers={"X-Request-ID": "test-rid-123"})
    assert response.headers.get("X-Request-ID") == "test-rid-123"
