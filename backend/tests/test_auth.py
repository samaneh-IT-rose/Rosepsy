import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import engine
from app.core.phone import normalize_iran_mobile
from app.main import app
from app.services.sms import get_sms_sender

client = TestClient(app)


def _request_otp(phone: str):
    return client.post("/api/v1/auth/otp/request", json={"phone": phone})


def _last_code(phone: str) -> str:
    """Mock stores the NORMALIZED (E.164) number; look it up accordingly."""
    target = normalize_iran_mobile(phone)
    sent = [s for s in get_sms_sender().sent if s["phone"] == target]
    assert sent, f"no mock SMS captured for {target}"
    return sent[-1]["code"]


def _verify(challenge_id: str, code: str):
    return client.post(
        "/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )


def test_otp_request_returns_challenge_without_code():
    phone = "09121110001"
    resp = _request_otp(phone)
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] is None
    assert body["data"]["expires_in_seconds"] == 120
    assert body["data"]["challenge_id"]
    assert _last_code(phone) not in resp.text  # the code never leaks over HTTP


def test_verify_creates_user_session_and_profile():
    phone = "09121110002"
    cid = _request_otp(phone).json()["data"]["challenge_id"]
    v = _verify(cid, _last_code(phone))
    assert v.status_code == 200
    data = v.json()["data"]
    assert data["is_new_user"] is True
    assert data["token_type"] == "bearer"
    assert data["access_token"]

    me = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["data"]["phone"] == "+989121110002"
    assert me.json()["data"]["roles"] == []


def test_used_code_cannot_be_reused():
    phone = "09121110003"
    cid = _request_otp(phone).json()["data"]["challenge_id"]
    code = _last_code(phone)
    assert _verify(cid, code).status_code == 200
    second = _verify(cid, code)
    assert second.status_code == 409
    assert second.json()["errors"][0]["code"] == "OTP_ALREADY_USED"


def test_wrong_code_locks_after_max_attempts():
    phone = "09121110004"
    cid = _request_otp(phone).json()["data"]["challenge_id"]
    for _ in range(4):
        assert _verify(cid, "000000").status_code == 401
    locked = _verify(cid, "000000")
    assert locked.status_code == 423
    assert locked.json()["errors"][0]["code"] == "OTP_LOCKED"
    assert _verify(cid, _last_code(phone)).status_code == 423  # locked even if correct


def test_expired_code_rejected():
    phone = "09121110005"
    cid = _request_otp(phone).json()["data"]["challenge_id"]
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE core.otp_challenges SET expires_at = now() - interval '1 minute'")
        )
    resp = _verify(cid, _last_code(phone))
    assert resp.status_code == 400
    assert resp.json()["errors"][0]["code"] == "OTP_EXPIRED"


def test_new_request_supersedes_previous_code():
    phone = "09121110006"
    first = _request_otp(phone).json()["data"]
    second = _request_otp(phone).json()["data"]
    assert first["challenge_id"] != second["challenge_id"]
    stale = _verify(first["challenge_id"], _last_code(phone))
    assert stale.status_code == 400
    assert stale.json()["errors"][0]["code"] == "OTP_EXPIRED"
    assert _verify(second["challenge_id"], _last_code(phone)).status_code == 200


def test_me_requires_token():
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["errors"][0]["code"] == "UNAUTHORIZED"


def test_request_rate_limit_per_phone():
    phone = "09121110007"
    for _ in range(3):
        assert _request_otp(phone).status_code == 200
    limited = _request_otp(phone)
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After")
    assert limited.json()["errors"][0]["code"] == "RATE_LIMITED"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("09121110008", "+989121110008"),
        ("+989121110009", "+989121110009"),
        ("00989121110010", "+989121110010"),
        ("989121110011", "+989121110011"),
        ("0912 111 0012", "+989121110012"),
    ],
)
def test_phone_normalization(raw, expected):
    assert normalize_iran_mobile(raw) == expected


def test_invalid_phone_rejected():
    # 10 chars (passes schema length) but not a mobile pattern -> our domain error
    resp = _request_otp("1234567890")
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "INVALID_PHONE"


def test_too_short_phone_fails_schema_validation():
    # Below min_length -> generic VALIDATION_ERROR from the contract handler
    resp = _request_otp("12345")
    assert resp.status_code == 422
    err = resp.json()["errors"][0]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == "phone"


def test_empty_code_fails_schema_validation():
    phone = "09121110013"
    cid = _request_otp(phone).json()["data"]["challenge_id"]
    resp = _verify(cid, "")
    assert resp.status_code == 422
    err = resp.json()["errors"][0]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == "code"


def test_uuid7_layout():
    from app.core.ids import uuid7

    assert uuid7().version == 7
