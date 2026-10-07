import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import envelope, error_response
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.booking import Appointment, SlotClaim
from app.models.catalog import Consultant, Service
from app.models.core import User
from app.services.authz import write_audit
from app.services.booking import (
    consultant_is_bookable,
    expire_stale_holds,
    price_snapshot,
    validate_hold_window,
)

router = APIRouter(tags=["booking"])

CANCELLABLE = ("pending_payment", "confirmed")


class HoldIn(BaseModel):
    consultant_id: uuid.UUID
    service_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    start_at: datetime
    duration_minutes: int | None = Field(default=None, gt=0, le=600)


class AppointmentIn(BaseModel):
    hold_id: uuid.UUID


def _hold_data(c: SlotClaim) -> dict:
    return {
        "id": str(c.id),
        "consultant_id": str(c.consultant_id),
        "service_id": str(c.service_id),
        "branch_id": str(c.branch_id) if c.branch_id else None,
        "start_at": c.start_at.isoformat(),
        "end_at": c.end_at.isoformat(),
        "expires_at": c.expires_at.isoformat(),
        "price_snapshot": c.price_snapshot,
    }


def _appointment_data(a: Appointment) -> dict:
    return {
        "id": str(a.id),
        "user_id": str(a.user_id),
        "consultant_id": str(a.consultant_id),
        "service_id": str(a.service_id),
        "branch_id": str(a.branch_id) if a.branch_id else None,
        "start_at": a.start_at.isoformat(),
        "end_at": a.end_at.isoformat(),
        "status": a.status,
        "price_snapshot": a.price_snapshot,
        "created_at": a.created_at.isoformat(),
    }


@router.post("/booking-holds", status_code=201)
def create_hold(
    body: HoldIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Temporary slot hold with TTL (B09)."""
    now = datetime.now(UTC)
    expire_stale_holds(db)

    consultant = db.get(Consultant, body.consultant_id)
    if consultant is None:
        return error_response("CONSULTANT_NOT_FOUND", "مشاور یافت نشد", 404)
    if not consultant_is_bookable(db, consultant):
        return error_response("CONSULTANT_NOT_BOOKABLE", "این مشاور در حال حاضر قابل رزرو نیست", 409)
    service = db.get(Service, body.service_id)
    if service is None or not service.is_active:
        return error_response("SERVICE_NOT_FOUND", "خدمت یافت نشد یا غیرفعال است", 404)
    if body.duration_minutes is not None and body.duration_minutes != service.duration_minutes:
        return error_response(
            "DURATION_MISMATCH",
            f"مدت این خدمت {service.duration_minutes} دقیقه است",
            422,
            field="duration_minutes",
        )

    start_at = body.start_at
    if start_at.tzinfo is None:
        return error_response(
            "VALIDATION_ERROR", "زمان باید شامل منطقه زمانی (UTC) باشد", 422, field="start_at"
        )
    start_at = start_at.astimezone(UTC)
    end_at = start_at + timedelta(minutes=service.duration_minutes)

    err = validate_hold_window(
        db,
        service=service,
        consultant_id=consultant.id,
        tz_name=settings.AVAILABILITY_TIMEZONE,
        start_at=start_at,
        now=now,
        max_advance_days=settings.BOOKING_MAX_ADVANCE_DAYS,
    )
    if err == "SLOT_IN_PAST":
        return error_response("SLOT_IN_PAST", "زمان انتخابی در گذشته است", 422)
    if err == "RANGE_TOO_LONG":
        return error_response(
            "RANGE_TOO_LONG",
            f"حداکثر {settings.BOOKING_MAX_ADVANCE_DAYS} روز آینده قابل رزرو است",
            422,
        )
    if err == "SLOT_UNAVAILABLE":
        return error_response("SLOT_UNAVAILABLE", "این زمان با تقویم مشاور هم‌خوان نیست", 409)
    if err == "SLOT_TAKEN":
        return error_response("SLOT_TAKEN", "این زمان قبلا رزرو یا نگهداری شده است", 409)

    snapshot = price_snapshot(db, service_id=service.id, branch_id=body.branch_id, at=now)
    claim = SlotClaim(
        user_id=user.id,
        consultant_id=consultant.id,
        service_id=service.id,
        branch_id=body.branch_id,
        start_at=start_at,
        end_at=end_at,
        expires_at=now + timedelta(seconds=settings.BOOKING_HOLD_TTL_SECONDS),
        price_snapshot=snapshot,
    )
    db.add(claim)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return error_response("SLOT_TAKEN", "این زمان هم‌اکنون گرفته شد", 409)
    return envelope(data=_hold_data(claim))


@router.post("/appointments", status_code=201)
def create_appointment(
    body: AppointmentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Finalize an appointment from an active hold (B09)."""
    now = datetime.now(UTC)
    expire_stale_holds(db)

    claim = db.get(SlotClaim, body.hold_id)
    if claim is None or claim.user_id != user.id:
        return error_response("HOLD_NOT_FOUND", "نگهداری موقت یافت نشد", 404)
    if claim.status == "consumed":
        return error_response("HOLD_ALREADY_USED", "این نگهداری قبلا مصرف شده است", 409)
    if claim.expires_at <= now:
        return error_response("HOLD_EXPIRED", "مهلت نگهداری به پایان رسیده است", 409)
    if claim.status != "held":
        return error_response("HOLD_NOT_ACTIVE", "این نگهداری دیگر فعال نیست", 409)

    service = db.get(Service, claim.service_id)
    # consume FIRST so this very hold is not counted as an active overlap below
    claim.status = "consumed"
    db.commit()

    err = validate_hold_window(
        db,
        service=service,
        consultant_id=claim.consultant_id,
        tz_name=settings.AVAILABILITY_TIMEZONE,
        start_at=claim.start_at,
        now=now,
        max_advance_days=settings.BOOKING_MAX_ADVANCE_DAYS,
    )
    if err is not None:
        claim.status = "released"
        db.commit()
        return error_response("SLOT_TAKEN", "زمان نگهداری دیگر معتبر نیست", 409)

    snapshot = claim.price_snapshot or price_snapshot(
        db, service_id=claim.service_id, branch_id=claim.branch_id, at=now
    )
    status = "confirmed" if not snapshot else "pending_payment"
    appointment = Appointment(
        user_id=user.id,
        consultant_id=claim.consultant_id,
        service_id=claim.service_id,
        branch_id=claim.branch_id,
        hold_id=claim.id,
        start_at=claim.start_at,
        end_at=claim.end_at,
        status=status,
        price_snapshot=snapshot,
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return error_response("SLOT_TAKEN", "این زمان هم‌اکنون گرفته شد", 409)
    write_audit(
        db,
        actor_user_id=user.id,
        action="appointment.create",
        outcome="allowed",
        resource_type="appointment",
        resource_id=appointment.id,
        request_id=request_id_var.get(),
        detail={"status": status},
    )
    return envelope(data=_appointment_data(appointment))


@router.get("/appointments")
def my_appointments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(
            select(Appointment)
            .where(Appointment.user_id == user.id)
            .order_by(Appointment.start_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return envelope(data=[_appointment_data(a) for a in rows])


@router.get("/appointments/{appointment_id}")
def get_appointment(
    appointment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.get(Appointment, appointment_id)
    if a is None or a.user_id != user.id:
        return error_response("APPOINTMENT_NOT_FOUND", "نوبت یافت نشد", 404)
    return envelope(data=_appointment_data(a))


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: uuid.UUID,
    reason: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.get(Appointment, appointment_id)
    if a is None or a.user_id != user.id:
        return error_response("APPOINTMENT_NOT_FOUND", "نوبت یافت نشد", 404)
    if a.status not in CANCELLABLE:
        return error_response("INVALID_TRANSITION", f"لغو از وضعیت {a.status} مجاز نیست", 409)
    a.status = "cancelled"
    a.cancelled_at = datetime.now(UTC)
    a.cancel_reason = (reason or "-")[:300]
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="appointment.cancel",
        outcome="allowed",
        resource_type="appointment",
        resource_id=a.id,
        request_id=request_id_var.get(),
    )
    return envelope(data={"id": str(a.id), "status": a.status})
