"""Booking core (B09): eligibility, block gathering, hold expiry, price snapshot."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.availability import AvailabilityException, WeeklyRule
from app.models.booking import Appointment, SlotClaim
from app.models.catalog import Consultant, Credential, Service
from app.services.pricing import applicable_version, find_tariff
from app.services.slots import generate_slots

ACTIVE_APPOINTMENT_STATUSES = ("pending_payment", "confirmed", "in_progress")


def consultant_is_bookable(db: Session, consultant: Consultant) -> bool:
    """approved status AND at least one verified, unexpired credential (spec B05)."""
    if consultant.status != "approved":
        return False
    now = datetime.now(UTC)
    stmt = (
        select(Credential.id)
        .where(
            Credential.consultant_id == consultant.id,
            Credential.status == "verified",
            (Credential.expires_at.is_(None)) | (Credential.expires_at >= now),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def expire_stale_holds(db: Session) -> int:
    """Release expired holds lazily (spec: 'hold منقضی آزاد شود')."""
    now = datetime.now(UTC)
    stale = (
        db.execute(
            select(SlotClaim).where(SlotClaim.status == "held", SlotClaim.expires_at <= now)
        )
        .scalars()
        .all()
    )
    for claim in stale:
        claim.status = "expired"
    if stale:
        db.commit()
    return len(stale)


def active_blocks(db: Session, consultant_id: uuid.UUID) -> list[tuple[datetime, datetime]]:
    """Everything that occupies the calendar: exceptions + active holds + active appointments."""
    blocks: list[tuple[datetime, datetime]] = []
    for x in (
        db.execute(
            select(AvailabilityException).where(
                AvailabilityException.consultant_id == consultant_id
            )
        )
        .scalars()
        .all()
    ):
        blocks.append((x.start_at, x.end_at))
    for c in (
        db.execute(
            select(SlotClaim).where(
                SlotClaim.consultant_id == consultant_id, SlotClaim.status == "held"
            )
        )
        .scalars()
        .all()
    ):
        blocks.append((c.start_at, c.end_at))
    for a in (
        db.execute(
            select(Appointment).where(
                Appointment.consultant_id == consultant_id,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            )
        )
        .scalars()
        .all()
    ):
        blocks.append((a.start_at, a.end_at))
    return blocks


def calendar_blocks_only(db: Session, consultant_id: uuid.UUID):
    """Availability exceptions only (for window validation, before occupancy)."""
    return [
        (x.start_at, x.end_at)
        for x in db.execute(
            select(AvailabilityException).where(
                AvailabilityException.consultant_id == consultant_id
            )
        )
        .scalars()
        .all()
    ]


def window_has_slot(
    db: Session,
    *,
    consultant_id: uuid.UUID,
    service: Service,
    tz_name: str,
    now: datetime,
    start_at: datetime,
) -> bool:
    """True if start_at exactly matches a slot generated from rules minus exceptions."""
    tz = ZoneInfo(tz_name)
    day = start_at.astimezone(tz).date()
    rules = [
        (r.weekday, r.start_time, r.end_time)
        for r in db.execute(
            select(WeeklyRule).where(
                WeeklyRule.consultant_id == consultant_id, WeeklyRule.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    ]
    slots_map = generate_slots(
        rules=rules,
        exceptions=calendar_blocks_only(db, consultant_id),
        duration_minutes=service.duration_minutes,
        tz_name=tz_name,
        now=now,
        from_date=day,
        to_date=day,
    )
    for slot in slots_map.get(day.isoformat(), []):
        if datetime.fromisoformat(slot["start"]) == start_at:
            return True
    return False


def overlaps_active(db: Session, *, consultant_id: uuid.UUID, start_at, end_at) -> bool:
    blocks = active_blocks(db, consultant_id)
    return any(start < end_at and start_at < end for start, end in blocks)


def price_snapshot(
    db: Session, *, service_id: uuid.UUID, branch_id: uuid.UUID | None, at: datetime
) -> dict | None:
    """Snapshot for hold/appointment; None means the service is free."""
    tariff = find_tariff(db, service_id=service_id, branch_id=branch_id)
    if tariff is None:
        return None
    version = applicable_version(db, tariff=tariff, at=at)
    if version is None:
        return None
    amount = int(version.amount)
    if amount <= 0:
        return None
    return {
        "amount": amount,
        "currency": version.currency,
        "tariff_id": str(tariff.id),
        "version_id": str(version.id),
        "quoted_at": at.isoformat(),
    }


def validate_hold_window(
    db: Session,
    *,
    service: Service,
    consultant_id: uuid.UUID,
    tz_name: str,
    start_at: datetime,
    now: datetime,
    max_advance_days: int,
) -> str | None:
    """Returns an error code or None. Assumes end_at = start + service duration."""
    if start_at < now:
        return "SLOT_IN_PAST"
    tz = ZoneInfo(tz_name)
    start_day = start_at.astimezone(tz).date()
    if start_day > now.astimezone(tz).date() + timedelta(days=max_advance_days):
        return "RANGE_TOO_LONG"
    if not window_has_slot(
        db,
        consultant_id=consultant_id,
        service=service,
        tz_name=tz_name,
        now=now,
        start_at=start_at,
    ):
        return "SLOT_UNAVAILABLE"
    if overlaps_active(
        db,
        consultant_id=consultant_id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=service.duration_minutes),
    ):
        return "SLOT_TAKEN"
    return None
