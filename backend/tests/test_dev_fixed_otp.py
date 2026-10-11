from fastapi.testclient import TestClient

import app.api.auth as auth_mod
import app.services.sms as sms_mod
from app.main import app
from app.services.sms import DevFixedSmsSender

client = TestClient(app)


def _fixed_sender() -> DevFixedSmsSender:
    return DevFixedSmsSender("123456")


def test_dev_fixed_code_accepted(monkeypatch):
    """In dev_fixed mode, the known code signs the user in without the log."""
    monkeypatch.setenv("SMS_PROVIDER", "dev_fixed")
    monkeypatch.setattr(sms_mod, "get_sms_sender", _fixed_sender)
    monkeypatch.setattr(auth_mod, "get_sms_sender", _fixed_sender)

    r = client.post("/api/v1/auth/otp/request", json={"phone": "09129990001"})
    assert r.status_code == 200

    v = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": r.json()["data"]["challenge_id"], "code": "123456"},
    )
    assert v.status_code == 200, v.text
    assert v.json()["data"]["access_token"]


def test_wrong_code_still_rejected_in_dev_fixed(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "dev_fixed")
    monkeypatch.setattr(sms_mod, "get_sms_sender", _fixed_sender)
    monkeypatch.setattr(auth_mod, "get_sms_sender", _fixed_sender)

    r = client.post("/api/v1/auth/otp/request", json={"phone": "09129990002"})
    v = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": r.json()["data"]["challenge_id"], "code": "000000"},
    )
    assert v.status_code == 401
