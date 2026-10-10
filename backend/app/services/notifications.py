"""Notification core (B12/B38): templates, outbox, retryable delivery.

- enqueue_event(): NO commit; caller commits with the state change.
- process_outbox(): template-render -> in-app notification -> channel delivery.
  Delivery failure increments attempts; after NOTIF_MAX_ATTEMPTS the event is
  marked failed (recorded, retryable manually later) - spec B38.
- Body/title carry IDs/codes only; never clinical content (B38 rule).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notify import CommunicationPreference, Notification, NotificationEvent

logger = logging.getLogger("roz.notify")


def _fmt(v) -> str:
    return str(v) if v is not None else "-"


def _payment_body(p: dict) -> str:
    order_id = _fmt(p.get("order_id"))
    amount = _fmt(p.get("amount"))
    return f"سفارش {order_id} به مبلغ {amount} پرداخت شد"


def _cancellation_body(p: dict) -> str:
    appointment_id = _fmt(p.get("appointment_id"))
    return f"نوبت {appointment_id} لغو شد"


TEMPLATES: dict[str, dict] = {
    "payment.success": {
        "title_fa": "پرداخت تأیید شد",
        "body": _payment_body,
    },
    "appointment.cancelled": {
        "title_fa": "نوبت لغو شد",
        "body": _cancellation_body,
    },
}
FALLBACK_TITLE = "اطلاع‌رسانی سامانه"


def render(event_type: str, payload: dict) -> tuple[str, str]:
    tpl = TEMPLATES.get(event_type)
    if tpl is None:
        body = ", ".join(f"{k}={v}" for k, v in sorted(payload.items())) or "-"
        return FALLBACK_TITLE, body
    return tpl["title_fa"], tpl["body"](payload)


def enqueue_event(
    db: Session, *, user_id, event_type: str, payload: dict
) -> NotificationEvent:
    event = NotificationEvent(user_id=user_id, event_type=event_type, payload=payload)
    db.add(event)
    return event


def _deliver(user_id, event_type: str, body: str) -> bool:
    """Channel delivery (mock until D02/D04). Returns success bool; never raises."""
    try:
        logger.info(
            "notify delivered user=%s event=%s body=%s", user_id, event_type, body
        )
        return True
    except Exception:  # pragma: no cover - defensive
        logger.warning("notify delivery failed", exc_info=True)
        return False


def process_outbox(db: Session, limit: int = 100) -> dict:
    """Drain pending events. Returns {processed, retried, failed}."""
    events = (
        db.execute(
            select(NotificationEvent)
            .where(NotificationEvent.status == "pending")
            .order_by(NotificationEvent.created_at)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    processed = retried = failed = 0
    for event in events:
        title, body = render(event.event_type, event.payload)
        ok = _deliver(event.user_id, event.event_type, body)
        if ok:
            db.add(
                Notification(
                    user_id=event.user_id,
                    event_type=event.event_type,
                    title=title,
                    body=body[:500],
                )
            )
            event.status = "processed"
            event.processed_at = datetime.now(UTC)
            event.last_error = None
            processed += 1
            continue
        event.attempts += 1
        event.last_error = "channel_delivery_failed"
        if event.attempts >= settings.NOTIF_MAX_ATTEMPTS:
            event.status = "failed"
            failed += 1
            logger.warning(
                "notify gave up event=%s attempts=%s", event.id, event.attempts
            )
        else:
            retried += 1
            logger.info(
                "notify will retry event=%s attempts=%s", event.id, event.attempts
            )
    if processed or retried or failed:
        db.commit()
    return {"processed": processed, "retried": retried, "failed": failed}


def get_or_create_preferences(db: Session, user_id) -> CommunicationPreference:
    pref = db.get(CommunicationPreference, user_id)
    if pref is None:
        pref = CommunicationPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref