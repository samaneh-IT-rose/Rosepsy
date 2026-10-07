from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h, login

PHONE = iter(range(9141170000, 9141179999))
TZ = ZoneInfo("Asia/Tehran")


def _phone() -> str:
    return "0" + str(next(PHONE))


def _next_monday() -> datetime:
    today = datetime.now(timezone.utc).date()
    days_ahead = (0 - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead else 7
    return datetime.combine(today + timedelta(days=days_ahead), time(9, 0), tzinfo=TZ)


def _setup():
    """admin + eligible consultant + 45min service + Monday 09:00-12:00 rule."""
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر رزرو"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={"kind": "license", "title": "پروانه", "license_number": "LIC-B09"},
        headers=hok,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "approved"},
        headers=hok,
    )
    sid = client.post(
        "/api/v1/services",
        json={"name": "خدمت رزرو", "duration_minutes": 45},
        headers=hok,
    ).json()["data"]["id"]
    client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]},
        headers=hok,
    )
    return token, hok, cid, sid


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _hold(hok, cid, sid, start: datetime, branch=None):
    body = {"consultant_id": cid, "service_id": sid, "start_at": _utc(start)}
    if branch:
        body["branch_id"] = branch
    return client.post("/api/v1/booking-holds", json=body, headers=hok)


def _mk_user() -> tuple[str, dict]:
    tok, _ = login(_phone())
    return tok, h(tok)


# ---------- holds ----------


def test_hold_created_with_ttl():
    _, hok, cid, sid = _setup()
    r = _hold(hok, cid, sid, _next_monday())
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["status"] if "status" in data else True
    expires = datetime.fromisoformat(data["expires_at"])
    ttl_seconds = (expires - datetime.now(timezone.utc)).total_seconds()
    assert 550 <= ttl_seconds <= 600  # ~10min TTL from request time


def test_hold_outside_rules_rejected():
    _, hok, cid, sid = _setup()
    off_window = _next_monday().replace(hour=20)  # rules are 09-12
    r = _hold(hok, cid, sid, off_window)
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "SLOT_UNAVAILABLE"


def test_hold_in_past_rejected():
    _, hok, cid, sid = _setup()
    past = datetime.now(TZ) - timedelta(days=7)
    r = _hold(hok, cid, sid, past)
    assert r.status_code == 422
    assert r.json()["errors"][0]["code"] == "SLOT_IN_PAST"


def test_second_hold_same_slot_conflicts():
    _, hok, cid, sid = _setup()
    start = _next_monday()
    first = _hold(hok, cid, sid, start)
    assert first.status_code == 201
    u2, h2 = _mk_user()
    second = _hold(h2, cid, sid, start)
    assert second.status_code == 409
    assert second.json()["errors"][0]["code"] == "SLOT_TAKEN"


def test_hold_for_unbookable_consultant_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "تأییدنشده"}, headers=hok
    ).json()["data"]["id"]
    sid = client.post(
        "/api/v1/services", json={"name": "خدمت بدون مشاور مجاز", "duration_minutes": 30},
        headers=hok,
    ).json()["data"]["id"]
    r = _hold(hok, cid, sid, _next_monday())
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "CONSULTANT_NOT_BOOKABLE"


def test_expired_hold_frees_slot():
    _, hok, cid, sid = _setup()
    start = _next_monday()
    first = _hold(hok, cid, sid, start).json()["data"]
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE booking.slot_claims SET expires_at = now() - interval '1 minute'")
        )
    u2, h2 = _mk_user()
    again = _hold(h2, cid, sid, start)
    assert again.status_code == 201  # expired hold released the slot
    # consuming the expired first hold fails
    v = client.post("/api/v1/appointments", json={"hold_id": first["id"]}, headers=hok)
    assert v.status_code == 409
    assert v.json()["errors"][0]["code"] == "HOLD_EXPIRED"


# ---------- appointments ----------


def test_free_service_appointment_is_confirmed():
    _, hok, cid, sid = _setup()  # no tariff -> free
    start = _next_monday()
    hold = _hold(hok, cid, sid, start).json()["data"]
    a = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    assert a.status_code == 201, a.text
    assert a.json()["data"]["status"] == "confirmed"
    assert a.json()["data"]["price_snapshot"] is None
    # hold consumed -> reuse fails
    again = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "HOLD_ALREADY_USED"


def test_paid_service_appointment_pending_payment():
    _, hok, cid, sid = _setup()
    tid = client.post("/api/v1/tariffs", json={"service_id": sid}, headers=hok).json()["data"]["id"]
    client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 4500000, "valid_from": "2024-01-01T00:00:00Z"},
        headers=hok,
    )
    start = _next_monday()
    hold = _hold(hok, cid, sid, start).json()["data"]
    assert hold["price_snapshot"]["amount"] == 4500000  # snapshot at hold time
    a = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    assert a.status_code == 201
    assert a.json()["data"]["status"] == "pending_payment"
    assert a.json()["data"]["price_snapshot"]["version_id"] == hold["price_snapshot"]["version_id"]


def test_hold_of_another_user_not_usable():
    _, hok, cid, sid = _setup()
    hold = _hold(hok, cid, sid, _next_monday()).json()["data"]
    u2, h2 = _mk_user()
    r = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=h2)
    assert r.status_code == 404  # no leakage of others' holds


def test_appointment_blocks_slot_and_cancel_frees():
    _, hok, cid, sid = _setup()
    start = _next_monday()
    hold = _hold(hok, cid, sid, start).json()["data"]
    a = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    assert a.status_code == 201
    aid = a.json()["data"]["id"]
    u2, h2 = _mk_user()
    blocked = _hold(h2, cid, sid, start)
    assert blocked.status_code == 409
    assert blocked.json()["errors"][0]["code"] == "SLOT_TAKEN"
    cancel = client.post(f"/api/v1/appointments/{aid}/cancel", headers=hok)
    assert cancel.status_code == 200
    freed = _hold(h2, cid, sid, start)
    assert freed.status_code == 201
    again = client.post(f"/api/v1/appointments/{aid}/cancel", headers=hok)
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "INVALID_TRANSITION"


def test_availability_subtracts_booked_appointment():
    _, hok, cid, sid = _setup()
    start = _next_monday()
    monday = start.date().isoformat()
    hold = _hold(hok, cid, sid, start).json()["data"]
    client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    slots = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid, "from": monday, "to": monday},
        headers=hok,
    ).json()["data"]["dates"]
    starts = [s["start"] for s in slots[monday]]
    assert start.astimezone(timezone.utc).isoformat() not in starts
    assert len(starts) == 3  # 09:00 taken, 09:45/10:30/10:15... 45min in 3h = 4 slots - 1 = 3


def test_my_appointments_list():
    _, hok, cid, sid = _setup()
    hold = _hold(hok, cid, sid, _next_monday()).json()["data"]
    client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    listing = client.get("/api/v1/appointments", headers=hok)
    assert listing.status_code == 200
    assert len(listing.json()["data"]) == 1
    u2, h2 = _mk_user()
    assert client.get("/api/v1/appointments", headers=h2).json()["data"] == []


def test_naive_datetime_rejected():
    _, hok, cid, sid = _setup()
    naive = _next_monday().strftime("%Y-%m-%dT%H:%M:%S")
    r = client.post(
        "/api/v1/booking-holds",
        json={"consultant_id": cid, "service_id": sid, "start_at": naive},
        headers=hok,
    )
    assert r.status_code == 422
