import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.availability import AvailabilityException, WeeklyRule
from app.models.catalog import Consultant, Service
from app.models.core import User
from app.services.authz import has_permission, write_audit
from app.services.slots import generate_slots

router = APIRouter(tags=["availability"])

MAX_RANGE_DAYS = 31


class RuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    branch_id: uuid.UUID | None = None


class RulesPutIn(BaseModel):
    rules: list[RuleIn] = Field(max_length=70)

    @model_validator(mode="after")
    def _windows_ok(self):
        for r in self.rules:
            if r.end_time <= r.start_time:
                raise ValueError("end_time must be after start_time")
        return self


class ExceptionIn(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _ok(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.end_at - self.start_at > timedelta(days=366):
            raise ValueError("exception window too long (max 366 days)")
        return self


def _consultant_or_404(db: Session, consultant_id: uuid.UUID):
    consultant = db.get(Consultant, consultant_id)
    if consultant is None:
        return None, error_response("CONSULTANT_NOT_FOUND", "مشاور یافت نشد", 404)
    return consultant, None


def _authorize(db: Session, user: User, consultant: Consultant):
    """system_admin manages any calendar; a consultant manages only their own."""
    if has_permission(db, user.id, "consultants.manage"):
        return None
    own = db.execute(
        select(Consultant).where(Consultant.user_id == user.id)
    ).scalar_one_or_none()
    if own is not None and own.id == consultant.id:
        return None
    write_audit(
        db,
        actor_user_id=user.id,
        action="availability.manage",
        outcome="denied",
        resource_type="consultant",
        resource_id=consultant.id,
        request_id=request_id_var.get(),
    )
    return error_response("FORBIDDEN", "فقط تقویم خودتان را می‌توانید ویرایش کنید", 403)


@router.get("/consultants/{consultant_id}/availability-rules")
def get_rules(
    consultant_id: uuid.UUID,
    user: User = Depends(require_permission("availability.manage")),
    db: Session = Depends(get_db),
):
    consultant, err = _consultant_or_404(db, consultant_id)
    if err:
        return err
    denied = _authorize(db, user, consultant)
    if denied:
        return denied
    rows = (
        db.execute(
            select(WeeklyRule)
            .where(WeeklyRule.consultant_id == consultant_id, WeeklyRule.is_active.is_(True))
            .order_by(WeeklyRule.weekday, WeeklyRule.start_time)
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(r.id),
                "weekday": r.weekday,
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat(),
                "branch_id": str(r.branch_id) if r.branch_id else None,
            }
            for r in rows
        ]
    )


@router.put("/consultants/{consultant_id}/availability-rules")
def put_rules(
    consultant_id: uuid.UUID,
    body: RulesPutIn,
    user: User = Depends(require_permission("availability.manage")),
    db: Session = Depends(get_db),
):
    """Replace the whole weekly program (idempotent bulk write)."""
    consultant, err = _consultant_or_404(db, consultant_id)
    if err:
        return err
    denied = _authorize(db, user, consultant)
    if denied:
        return denied

    by_day: dict[int, list] = {}
    for r in body.rules:
        by_day.setdefault(r.weekday, []).append(r)
    for weekday, rules in by_day.items():
        ordered = sorted(rules, key=lambda r: r.start_time)
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt.start_time < prev.end_time:
                return error_response(
                    "OVERLAPPING_RULES", f"پنجره‌های هم‌پوشان در روز هفته {weekday}", 409
                )

    db.execute(delete(WeeklyRule).where(WeeklyRule.consultant_id == consultant_id))
    for r in body.rules:
        db.add(
            WeeklyRule(
                consultant_id=consultant_id,
                weekday=r.weekday,
                start_time=r.start_time,
                end_time=r.end_time,
                branch_id=r.branch_id,
            )
        )
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="availability.rules.replace",
        outcome="allowed",
        resource_type="consultant",
        resource_id=consultant_id,
        request_id=request_id_var.get(),
        detail={"rules": len(body.rules)},
    )
    return envelope(data={"replaced": len(body.rules)})


@router.post("/consultants/{consultant_id}/availability-exceptions", status_code=201)
def add_exception(
    consultant_id: uuid.UUID,
    body: ExceptionIn,
    user: User = Depends(require_permission("availability.manage")),
    db: Session = Depends(get_db),
):
    consultant, err = _consultant_or_404(db, consultant_id)
    if err:
        return err
    denied = _authorize(db, user, consultant)
    if denied:
        return denied
    exc = AvailabilityException(
        consultant_id=consultant_id,
        start_at=body.start_at,
        end_at=body.end_at,
        reason=body.reason,
        created_by=user.id,
    )
    db.add(exc)
    db.commit()
    return envelope(
        data={
            "id": str(exc.id),
            "start_at": exc.start_at.isoformat(),
            "end_at": exc.end_at.isoformat(),
        }
    )


@router.delete("/consultants/{consultant_id}/availability-exceptions/{exception_id}")
def delete_exception(
    consultant_id: uuid.UUID,
    exception_id: uuid.UUID,
    user: User = Depends(require_permission("availability.manage")),
    db: Session = Depends(get_db),
):
    consultant, err = _consultant_or_404(db, consultant_id)
    if err:
        return err
    denied = _authorize(db, user, consultant)
    if denied:
        return denied
    exc = db.execute(
        select(AvailabilityException).where(
            AvailabilityException.id == exception_id,
            AvailabilityException.consultant_id == consultant_id,
        )
    ).scalar_one_or_none()
    if exc is None:
        return error_response("EXCEPTION_NOT_FOUND", "استثنا یافت نشد", 404)
    db.delete(exc)
    db.commit()
    return envelope(data={"deleted": True})


@router.get("/consultants/{consultant_id}/availability")
def free_slots(
    consultant_id: uuid.UUID,
    service_id: uuid.UUID = Query(),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Free slots for a service over a date range (contract: /consultants/{id}/availability)."""
    consultant, err = _consultant_or_404(db, consultant_id)
    if err:
        return err
    service = db.get(Service, service_id)
    if service is None or not service.is_active:
        return error_response("SERVICE_NOT_FOUND", "خدمت یافت نشد یا غیرفعال است", 404)

    today = datetime.now(timezone.utc).date()
    start_d = from_ or today
    end_d = to or (start_d + timedelta(days=13))
    if end_d < start_d:
        return error_response("INVALID_RANGE", "بازه تاریخ نامعتبر است", 422)
    if (end_d - start_d).days > MAX_RANGE_DAYS:
        return error_response("RANGE_TOO_LONG", "حداکثر بازه ۳۱ روز است", 422)

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
    exceptions = [
        (x.start_at, x.end_at)
        for x in db.execute(
            select(AvailabilityException).where(
                AvailabilityException.consultant_id == consultant_id
            )
        )
        .scalars()
        .all()
    ]
    result = generate_slots(
        rules=rules,
        exceptions=exceptions,
        duration_minutes=service.duration_minutes,
        tz_name=settings.AVAILABILITY_TIMEZONE,
        now=datetime.now(timezone.utc),
        from_date=start_d,
        to_date=end_d,
    )
    return envelope(
        data={
            "consultant_id": str(consultant_id),
            "service_id": str(service_id),
            "duration_minutes": service.duration_minutes,
            "dates": result,
        }
    )
