from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.core.db import SessionLocal, engine
from app.models.clinical import ClinicalRecord, Encounter
from app.models.notify import NotificationEvent
from tests.helpers import client, grant, h

PHONE = iter(range(9141260000, 9141269999))
TZ = ZoneInfo("Asia/Tehran")


def _phone() -> str:
    return "0" + str(next(PHONE))


def _next_monday(hour: int) -> datetime:
    today = datetime.now(UTC).date()
    days_ahead = (0 - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead else 7
    return datetime.combine(today + timedelta(days=days_ahead), time(hour, 0), tzinfo=TZ)


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _setup():
    """admin + eligible consultant + 45min paid service (4.5M IRR) + Monday rule."""
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر اتومات"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={"kind": "license", "title": "پروانه", "license_number": "LIC-B19"},
        headers=hok,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "approved"},
        headers=hok,
    )
    sid = client.post(
        "/api/v1/services", json={"name": "خدمت اتومات", "duration_minutes": 45},
        headers=hok,
    ).json()["data"]["id"]
    tid = client.post("/api/v1/tariffs", json={"service_id": sid}, headers=hok).json()["data"]["id"]
    client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 4500000, "valid_from": "2024-01-01T00:00:00Z"},
        headers=hok,
    )
    client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]},
        headers=hok,
    )
    return token, hok, cid, sid


def _book_and_pay(hok, cid, sid, key, hour=9, with_consent=True):
    if with_consent:
        r = client.post("/api/v1/consents", json={"kind": "treatment"}, headers=hok)
        assert r.status_code == 201, r.text
    hold = client.post(
        "/api/v1/booking-holds",
        json={"consultant_id": cid, "service_id": sid, "start_at": _utc(_next_monday(hour))},
        headers=hok,
    ).json()["data"]
    appt = client.post(
        "/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        json={"appointment_id": appt["id"]},
        headers={**hok, "Idempotency-Key": key},
    ).json()["data"]
    start = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]
    cb = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    return appt, cb


def test_paid_auto_creates_record_and_encounter():
    token, hok, cid, sid = _setup()
    uid = client.get("/api/v1/me", headers=hok).json()["data"]["id"]
    appt, cb = _book_and_pay(hok, cid, sid, "s19-key-1")
    assert cb.status_code == 200, cb.text
    data = cb.json()["data"]
    assert data["order_status"] == "paid"
    assert data["fulfillment"]["record_created"] is True
    assert data["fulfillment"]["encounter_created"] is True

    with SessionLocal() as db:
        rec = db.execute(
            select(ClinicalRecord).where(ClinicalRecord.user_id == UUID(uid))
        ).scalar_one()
        enc = db.execute(
            select(Encounter).where(Encounter.appointment_id == UUID(appt["id"]))
        ).scalar_one()
        assert enc.status == "scheduled"
        assert str(enc.record_id) == str(rec.id)
        assert enc.consultant_id == UUID(cid)


def test_paid_without_consent_skips_clinical_and_notifies():
    token, hok, cid, sid = _setup()
    appt, cb = _book_and_pay(hok, cid, sid, "s19-key-2", with_consent=False)
    assert cb.status_code == 200
    data = cb.json()["data"]
    assert data["order_status"] == "paid"          # payment succeeds regardless
    assert data["fulfillment"]["record_created"] is False
    assert data["fulfillment"]["encounter_created"] is False
    assert data["fulfillment"]["reason"] == "consent_required"

    with SessionLocal() as db:
        ev = db.execute(
            select(NotificationEvent).where(
                NotificationEvent.event_type == "consent.required"
            )
        ).scalar_one()
        assert ev.status == "pending"
        assert ev.payload["appointment_id"] == appt["id"]
        records = db.execute(select(ClinicalRecord)).scalars().all()
        assert records == []   # no clinical data without consent (spec rule)


def test_existing_record_reused_not_duplicated():
    token, hok, cid, sid = _setup()
    # consent + manual record first (reception-style path)
    client.post("/api/v1/consents", json={"kind": "treatment"}, headers=hok)
    manual = client.post(
        "/api/v1/clinical-records",
        json={"user_id": client.get("/api/v1/me", headers=hok).json()["data"]["id"],
              "summary": "پرونده از قبل"},
        headers=hok,
    )
    assert manual.status_code == 201, manual.text
    existing_id = manual.json()["data"]["id"]

    appt, cb = _book_and_pay(hok, cid, sid, "s19-key-3", with_consent=False)
    data = cb.json()["data"]
    assert data["fulfillment"]["record_created"] is False   # reused
    assert data["fulfillment"]["encounter_created"] is True

    with SessionLocal() as db:
        enc = db.execute(
            select(Encounter).where(Encounter.appointment_id == UUID(appt["id"]))
        ).scalar_one()
        assert str(enc.record_id) == existing_id
        count = db.execute(select(ClinicalRecord)).scalars().all()
        assert len(count) == 1   # no duplicate record


def test_double_callback_does_not_duplicate_encounter():
    token, hok, cid, sid = _setup()
    client.post("/api/v1/consents", json={"kind": "treatment"}, headers=hok)
    hold = client.post(
        "/api/v1/booking-holds",
        json={"consultant_id": cid, "service_id": sid, "start_at": _utc(_next_monday(9))},
        headers=hok,
    ).json()["data"]
    appt = client.post(
        "/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok
    ).json()["data"]
    order = client.post(
        "/api/v1/orders",
        json={"appointment_id": appt["id"]},
        headers={**hok, "Idempotency-Key": "s19-key-4"},
    ).json()["data"]
    start = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]
    client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    second = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    assert second.json()["data"]["noop"] is True
    assert second.json()["data"].get("fulfillment") is None
    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM clinical.encounters WHERE appointment_id = :a"),
            {"a": UUID(appt["id"])},
        ).scalar_one()
    assert n == 1   # exactly one encounter despite repeated callback


def test_ineligible_consultant_notifies_admins():
    token, hok, cid, sid = _setup()
    client.post("/api/v1/consents", json={"kind": "treatment"}, headers=hok)
    hold = client.post(
        "/api/v1/booking-holds",
        json={"consultant_id": cid, "service_id": sid, "start_at": _utc(_next_monday(9))},
        headers=hok,
    ).json()["data"]
    appt = client.post(
        "/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok
    ).json()["data"]

    # credential expires AFTER booking but BEFORE payment
    with engine.begin() as conn:
        conn.execute(text("UPDATE core.credentials SET expires_at = now() - interval '1 day'"))

    order = client.post(
        "/api/v1/orders",
        json={"appointment_id": appt["id"]},
        headers={**hok, "Idempotency-Key": "s19-key-5"},
    ).json()["data"]
    start = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]
    cb = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    data = cb.json()["data"]
    assert data["order_status"] == "paid"
    assert data["fulfillment"]["record_created"] is True
    assert data["fulfillment"]["encounter_created"] is False
    assert data["fulfillment"]["reason"] == "consultant_not_eligible"

    with SessionLocal() as db:
        ev = db.execute(
            select(NotificationEvent).where(
                NotificationEvent.event_type == "encounter.auto_create_failed"
            )
        ).scalar_one()
        assert ev.status == "pending"
        assert ev.payload["appointment_id"] == appt["id"]
        encs = db.execute(select(Encounter)).scalars().all()
        assert encs == []
