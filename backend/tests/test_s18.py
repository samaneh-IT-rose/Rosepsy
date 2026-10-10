from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.notify import NotificationEvent
from app.services import notifications as notifsvc
from app.services.notifications import enqueue_event, process_outbox, render
from tests.helpers import client, h, login

PHONE = iter(range(9141250000, 9141259999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _paid_event():
    """Login a user and enqueue a payment.success event directly (outbox unit path)."""
    token, uid = login(_phone())
    with SessionLocal() as db:
        enqueue_event(
            db,
            user_id=uid,
            event_type="payment.success",
            payload={"order_id": "ord-1", "amount": 4500000},
        )
        db.commit()
    return token, uid


def _event_of(uid):
    with SessionLocal() as db:
        return db.execute(
            select(NotificationEvent).where(NotificationEvent.user_id == uid)
        ).scalar_one()


def test_template_rendering_persian_title_and_body():
    title, body = render("payment.success", {"order_id": "ord-9", "amount": 100})
    assert title == "پرداخت تأیید شد"
    assert "ord-9" in body and "100" in body
    t2, b2 = render("no.such.event", {"x": 1})
    assert t2 == "اطلاع‌رسانی سامانه" and "x=1" in b2


def test_outbox_uses_template_for_notification_title():
    token, uid = _paid_event()
    with SessionLocal() as db:
        process_outbox(db)
    listing = client.get("/api/v1/notifications", headers=h(token)).json()["data"]
    target = next(n for n in listing if n["event_type"] == "payment.success")
    assert target["title"] == "پرداخت تأیید شد"
    assert "سفارش ord-1" in target["body"]


def test_delivery_failure_retries_then_succeeds(monkeypatch):
    token, uid = _paid_event()
    monkeypatch.setattr(notifsvc, "_deliver", lambda *a, **k: False)
    with SessionLocal() as db:
        first = process_outbox(db)
        assert first["retried"] >= 1 and first["processed"] == 0
        ev = _event_of(uid)
        assert ev.status == "pending" and ev.attempts == 1  # recorded, stays pending

    monkeypatch.setattr(notifsvc, "_deliver", lambda *a, **k: True)
    with SessionLocal() as db:
        second = process_outbox(db)
        assert second["processed"] >= 1
        ev = _event_of(uid)
        assert ev.status == "processed" and ev.attempts == 1  # recovered on retry


def test_max_attempts_marks_failed(monkeypatch):
    token, uid = _paid_event()
    monkeypatch.setattr(notifsvc, "_deliver", lambda *a, **k: False)
    for _round in range(settings.NOTIF_MAX_ATTEMPTS):
        with SessionLocal() as db:
            process_outbox(db)
    ev = _event_of(uid)
    assert ev.status == "failed" and ev.attempts == settings.NOTIF_MAX_ATTEMPTS
    assert ev.last_error == "channel_delivery_failed"
    # failed events are no longer retried automatically
    res = process_outbox(db)
    assert res["retried"] == 0 and res["failed"] == 0
