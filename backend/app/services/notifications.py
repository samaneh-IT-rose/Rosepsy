"""Notification core (B12): outbox enqueue + dispatcher.

- enqueue_event(): NO commit here; the caller commits it together with the
  state change (transactional outbox per spec s.03).
- process_outbox(): converts pending events into in-app notifications and
  delivers via channels; body contains IDs/codes only - never clinical or
  free-form user content (B38 rule).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notify import CommunicationPreference, Notification, NotificationEvent

logger = logging.getLogger("roz.notify")


def enqueue_event(
    db: Session, *, user_id, event_type: str, payload: dict
) -> NotificationEvent:
    event = NotificationEvent(user_id=user_id, event_type=event_type, payload=payload)
    db.add(event)
    return event


def _deliver(user_id, event_type: str, body: str) -> None:
    """Channel delivery (mock until D04/D02 decisions). Transactional events
    always attempt delivery; failures are logged, never propagated."""
    try:
        logger.info("notify delivered user=%s event=%s body=%s", user_id, event_type, body)
    except Exception:  # pragma: no cover - defensive
        logger.warning("notify delivery failed", exc_info=True)


def process_outbox(db: Session, limit: int = 100) -> int:
    """Drain pending events -> notifications + channel delivery. Returns count."""
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
    processed = 0
    for event in events:
        body = ", ".join(f"{k}={v}" for k, v in sorted(event.payload.items())) or "-"
        db.add(
            Notification(
                user_id=event.user_id,
                event_type=event.event_type,
                title=event.event_type,
                body=body[:500],
            )
        )
        _deliver(event.user_id, event.event_type, body)
        event.status = "processed"
        event.processed_at = datetime.now(UTC)
        processed += 1
    if processed:
        db.commit()
    return processed


def get_or_create_preferences(db: Session, user_id) -> CommunicationPreference:
    pref = db.get(CommunicationPreference, user_id)
    if pref is None:
        pref = CommunicationPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref
