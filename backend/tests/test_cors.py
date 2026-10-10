from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_preflight_allowed_for_dev_origin():
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
