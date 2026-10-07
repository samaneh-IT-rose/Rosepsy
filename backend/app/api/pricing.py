import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.catalog import Service
from app.models.core import User
from app.models.org import Branch
from app.models.pricing import Tariff, TariffVersion
from app.services.authz import write_audit

router = APIRouter(tags=["pricing"])


class TariffIn(BaseModel):
    service_id: uuid.UUID
    branch_id: uuid.UUID | None = None


class VersionIn(BaseModel):
    amount: int = Field(gt=0, le=9_999_999_999_999)
    currency: str = Field(default="IRR", pattern=r"^[A-Z]{3}$")
    valid_from: datetime
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _range_ok(self):
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class VersionCloseIn(BaseModel):
    valid_to: datetime


def _overlap_exists(
    db: Session, tariff_id: uuid.UUID, v_from: datetime, v_to: datetime | None
) -> bool:
    """Half-open interval overlap: [a_from, a_to) vs [b_from, b_to)."""
    cond = or_(TariffVersion.valid_to.is_(None), TariffVersion.valid_to > v_from)
    if v_to is not None:
        cond = and_(cond, TariffVersion.valid_from < v_to)
    stmt = select(TariffVersion.id).where(TariffVersion.tariff_id == tariff_id, cond).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def _version_data(v: TariffVersion) -> dict:
    return {
        "id": str(v.id),
        "amount": int(v.amount),
        "currency": v.currency,
        "valid_from": v.valid_from.isoformat(),
        "valid_to": v.valid_to.isoformat() if v.valid_to else None,
    }


@router.post("/tariffs", status_code=201)
def create_tariff(
    body: TariffIn,
    user: User = Depends(require_permission("tariffs.manage")),
    db: Session = Depends(get_db),
):
    if db.get(Service, body.service_id) is None:
        return error_response("SERVICE_NOT_FOUND", "خدمت یافت نشد", 404)
    if body.branch_id is not None and db.get(Branch, body.branch_id) is None:
        return error_response("BRANCH_NOT_FOUND", "شعبه یافت نشد", 404)
    dup_cond = (
        Tariff.branch_id.is_(None)
        if body.branch_id is None
        else Tariff.branch_id == body.branch_id
    )
    dup = db.execute(
        select(Tariff).where(Tariff.service_id == body.service_id, dup_cond)
    ).scalar_one_or_none()
    if dup is not None:
        return error_response(
            "DUPLICATE_TARIFF",
            "برای این خدمت/شعبه قبلاً تعرفه ثبت شده است",
            409,
            details={"tariff_id": str(dup.id)},
        )
    t = Tariff(service_id=body.service_id, branch_id=body.branch_id)
    db.add(t)
    db.commit()
    return envelope(
        data={
            "id": str(t.id),
            "service_id": str(t.service_id),
            "branch_id": str(t.branch_id) if t.branch_id else None,
        }
    )


@router.get("/tariffs")
def list_tariffs(
    service_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(require_permission("tariffs.manage")),
    db: Session = Depends(get_db),
):
    stmt = select(Tariff)
    if service_id is not None:
        stmt = stmt.where(Tariff.service_id == service_id)
    rows = db.execute(stmt.order_by(Tariff.created_at)).scalars().all()
    data = []
    for t in rows:
        versions = (
            db.execute(
                select(TariffVersion)
                .where(TariffVersion.tariff_id == t.id)
                .order_by(TariffVersion.valid_from)
            )
            .scalars()
            .all()
        )
        data.append(
            {
                "id": str(t.id),
                "service_id": str(t.service_id),
                "branch_id": str(t.branch_id) if t.branch_id else None,
                "is_active": t.is_active,
                "versions": [_version_data(v) for v in versions],
            }
        )
    return envelope(data=data)


@router.post("/tariffs/{tariff_id}/versions", status_code=201)
def add_version(
    tariff_id: uuid.UUID,
    body: VersionIn,
    user: User = Depends(require_permission("tariffs.manage")),
    db: Session = Depends(get_db),
):
    tariff = db.get(Tariff, tariff_id)
    if tariff is None:
        return error_response("TARIFF_NOT_FOUND", "تعرفه یافت نشد", 404)
    if _overlap_exists(db, tariff_id, body.valid_from, body.valid_to):
        return error_response(
            "TARIFF_OVERLAP", "بازه اعتبار با نسخه موجود هم‌پوشانی دارد", 409
        )
    v = TariffVersion(
        tariff_id=tariff_id,
        amount=body.amount,
        currency=body.currency,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        created_by=user.id,
    )
    db.add(v)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="tariff.version.create",
        outcome="allowed",
        resource_type="tariff",
        resource_id=tariff_id,
        request_id=request_id_var.get(),
        detail={"version_id": str(v.id), "amount": body.amount},
    )
    return envelope(data=_version_data(v))


@router.patch("/tariffs/{tariff_id}/versions/{version_id}")
def close_version(
    tariff_id: uuid.UUID,
    version_id: uuid.UUID,
    body: VersionCloseIn,
    user: User = Depends(require_permission("tariffs.manage")),
    db: Session = Depends(get_db),
):
    """Close an open-ended version so a successor can start at that instant."""
    v = db.get(TariffVersion, version_id)
    if v is None or v.tariff_id != tariff_id:
        return error_response("VERSION_NOT_FOUND", "نسخه قیمت یافت نشد", 404)
    if v.valid_to is not None:
        return error_response("VERSION_ALREADY_CLOSED", "این نسخه قبلاً بسته شده است", 409)
    if body.valid_to <= v.valid_from:
        return error_response("INVALID_RANGE", "پایان بازه باید بعد از شروع آن باشد", 422)
    v.valid_to = body.valid_to
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="tariff.version.close",
        outcome="allowed",
        resource_type="tariff",
        resource_id=tariff_id,
        request_id=request_id_var.get(),
        detail={"version_id": str(v.id)},
    )
    return envelope(data=_version_data(v))


@router.get("/pricing/quote")
def quote(
    service_id: uuid.UUID,
    branch_id: uuid.UUID | None = Query(default=None),
    at: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Applicable price at a given instant; basis for the order price snapshot (S8).

    Branch-specific tariff wins over the service-global one.
    """
    at = at or datetime.now(UTC)
    tariff = None
    if branch_id is not None:
        tariff = db.execute(
            select(Tariff).where(
                Tariff.service_id == service_id,
                Tariff.branch_id == branch_id,
                Tariff.is_active.is_(True),
            )
        ).scalar_one_or_none()
    if tariff is None:
        tariff = db.execute(
            select(Tariff).where(
                Tariff.service_id == service_id,
                Tariff.branch_id.is_(None),
                Tariff.is_active.is_(True),
            )
        ).scalar_one_or_none()
    if tariff is None:
        return error_response("TARIFF_NOT_FOUND", "برای این خدمت تعرفه‌ای تعریف نشده است", 404)

    version = db.execute(
        select(TariffVersion)
        .where(
            TariffVersion.tariff_id == tariff.id,
            TariffVersion.valid_from <= at,
            or_(TariffVersion.valid_to.is_(None), TariffVersion.valid_to > at),
        )
        .order_by(TariffVersion.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        return error_response(
            "NO_APPLICABLE_VERSION", "در زمان خواسته‌شده قیمت اعمال‌شده‌ای وجود ندارد", 404
        )

    snapshot = _version_data(version)
    snapshot.update(
        {
            "service_id": str(service_id),
            "branch_id": str(branch_id) if branch_id else None,
            "tariff_id": str(tariff.id),
            "quoted_at": at.isoformat(),
        }
    )
    return envelope(data=snapshot)
