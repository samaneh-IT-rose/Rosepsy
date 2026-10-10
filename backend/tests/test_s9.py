from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.core.db import SessionLocal, engine
from app.models.notify import NotificationEvent
from app.services.notifications import process_outbox
from app.worker import process_outbox_task
from tests.helpers import client, grant, h, login

PHONE = iter(range(9141190000, 9141199999))
TZ = ZoneInfo("Asia/Tehran")


def _phone() -> str:
    return "0" + str(next(PHONE))


def _next_monday() -> datetime:
    today = datetime.now(UTC).date()
    days_ahead = (0 - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead else 7
    return datetime.combine(today + timedelta(days=days_ahead), time(9, 0), tzinfo=TZ)


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _pending_appointment(hok, cid, sid) -> dict:
    hold = client.post(
        "/api/v1/booking-holds",
        json={"consultant_id": cid, "service_id": sid, "start_at": _utc(_next_monday())},
        headers=hok,
    ).json()["data"]
    appt = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    assert appt.status_code == 201, appt.text
    return appt.json()["data"]


def _setup_paid():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر اعلان"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={"kind": "license", "title": "پروانه", "license_number": "LIC-B12"},
        headers=hok,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "approved"},
        headers=hok,
    )
    sid = client.post(
        "/api/v1/services", json={"name": "خدمت اعلان", "duration_minutes": 45},
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


def _paid_flow(key: str) -> tuple[dict, dict, str, str]:
    """Returns (hok, appt, order_id, invoice_id)."""
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
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
    ).json()["data"]
    return hok, appt, order["id"], cb["invoice_id"]


def test_callback_enqueues_outbox_event_pending():
    _, _, order_id, _ = _paid_flow("s9-key-1")
    with SessionLocal() as db:
        event = db.execute(
            select(NotificationEvent).where(
                NotificationEvent.event_type == "payment.success"
            )
        ).scalar_one()
        assert event.status == "pending"
        assert event.payload["order_id"] == order_id
        assert event.payload["amount"] == 4500000


def test_cancel_appointment_enqueues_event():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    client.post(f"/api/v1/appointments/{appt['id']}/cancel", headers=hok)
    with SessionLocal() as db:
        event = db.execute(
            select(NotificationEvent).where(
                NotificationEvent.event_type == "appointment.cancelled"
            )
        ).scalar_one()
        assert event.status == "pending"
        assert event.payload["appointment_id"] == appt["id"]


def test_outbox_processing_creates_notification():
    _paid_flow("s9-key-2")
    with SessionLocal() as db:
        n = process_outbox(db)
        assert n >= 1
        counts = db.execute(
            text(
                "SELECT status, count(*) FROM core.notification_events "
                "WHERE event_type = 'payment.success' GROUP BY status"
            )
        ).all()
        assert dict(counts)["processed"] >= 1
        assert "pending" not in dict(counts)


def test_notifications_listing_and_unread_meta():
    hok, _, _, _ = _paid_flow("s9-key-3")
    with SessionLocal() as db:
        process_outbox(db)
    listing = client.get("/api/v1/notifications", headers=hok)
    assert listing.status_code == 200
    data = listing.json()
    assert data["meta"]["unread"] >= 1
    assert any(x["event_type"] == "payment.success" for x in data["data"])


def test_mark_read_and_owner_scope():
    hok, _, _, _ = _paid_flow("s9-key-4")
    with SessionLocal() as db:
        process_outbox(db)
    nid = client.get("/api/v1/notifications", headers=hok).json()["data"][0]["id"]
    first = client.post(f"/api/v1/notifications/{nid}/read", headers=hok)
    assert first.status_code == 200
    again = client.post(f"/api/v1/notifications/{nid}/read", headers=hok)
    assert again.status_code == 200  # idempotent
    stranger, _ = login(_phone())
    resp = client.post(f"/api/v1/notifications/{nid}/read", headers=h(stranger))
    assert resp.status_code == 404  # not visible to others


def test_process_outbox_is_idempotent():
    _paid_flow("s9-key-5")
    with SessionLocal() as db:
        first = process_outbox(db)
        second = process_outbox(db)
    assert first >= 1
    assert second == 0  # nothing pending remains


def test_preferences_defaults_and_update():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    got = client.get("/api/v1/communication-preferences", headers=hok)
    assert got.status_code == 200
    assert got.json()["data"]["marketing_consent"] is False  # consent required by default
    put = client.put(
        "/api/v1/communication-preferences",
        json={"marketing_consent": True, "channel_sms": False},
        headers=hok,
    )
    assert put.json()["data"]["marketing_consent"] is True
    assert put.json()["data"]["channel_sms"] is False
    again = client.get("/api/v1/communication-preferences", headers=hok)
    assert again.json()["data"]["marketing_consent"] is True


def test_thread_membership_enforced():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    member_token, _ = login(_phone())
    created = client.post(
        "/api/v1/message-threads",
        json={"subject": "پیگیری رزرو", "member_ids": []},
        headers=hok,
    )
    assert created.status_code == 201
    tid = created.json()["data"]["id"]
    outsider, hout = login(_phone())
    denied = client.get(f"/api/v1/message-threads/{tid}/messages", headers=hout)
    assert denied.status_code == 404
    ok = client.get(f"/api/v1/message-threads/{tid}/messages", headers=hok)
    assert ok.status_code == 200
    my = client.get("/api/v1/message-threads", headers=h(member_token))
    assert my.json()["data"] == []


def test_message_post_and_view_member_only():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    tid = client.post(
        "/api/v1/message-threads",
        json={"subject": "سؤال مدارک", "member_ids": []},
        headers=hok,
    ).json()["data"]["id"]
    posted = client.post(
        f"/api/v1/message-threads/{tid}/messages",
        json={"body": "سلام، مدارک ارسال شد."},
        headers=hok,
    )
    assert posted.status_code == 201
    listed = client.get(f"/api/v1/message-threads/{tid}/messages", headers=hok)
    assert len(listed.json()["data"]) == 1
    outsider, hout = login(_phone())
    denied = client.post(
        f"/api/v1/message-threads/{tid}/messages",
        json={"body": "تلاش نفوذ"},
        headers=hout,
    )
    assert denied.status_code == 404


def test_notification_body_has_no_personal_data():
    """B38 rule: system notification text carries IDs/codes only."""
    hok, _, _, _ = _paid_flow("s9-key-6")
    with SessionLocal() as db:
        process_outbox(db)
    listing = client.get("/api/v1/notifications", headers=hok).json()["data"]
    target = next(n for n in listing if n["event_type"] == "payment.success")
    assert "order=" in target["body"]
    assert "دکتر اعلان" not in target["body"]  # no names, no clinical text


def test_worker_task_processes_outbox():
    _paid_flow("s9-key-7")
    result = process_outbox_task.apply()  # eager, no broker needed
    assert result.successful
    assert result.result["processed"] >= 1
    with engine.begin() as conn:
        pending = conn.execute(
            text("SELECT count(*) FROM core.notification_events WHERE status = 'pending'")
        ).scalar_one()
    assert pending == 0
