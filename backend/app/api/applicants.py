import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.core.phone import InvalidPhone, normalize_iran_mobile
from app.models.core import Applicant, User
from app.services.authz import write_audit

router = APIRouter(tags=["applicants"])


class ApplicantIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=10, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


def _applicant_data(a: Applicant) -> dict:
    return {
        "id": str(a.id),
        "full_name": a.full_name,
        "phone": a.phone_e164,
        "notes": a.notes,
        "created_by": str(a.created_by) if a.created_by else None,
        "created_at": a.created_at.isoformat(),
    }


@router.post("/applicants", status_code=201)
def create_applicant(
    body: ApplicantIn,
    user: User = Depends(require_permission("applicants.create")),
    db: Session = Depends(get_db),
):
    """Register an applicant WITHOUT a user account (B03); duplicates checked."""
    try:
        phone = normalize_iran_mobile(body.phone)
    except InvalidPhone:
        return error_response("INVALID_PHONE", "شماره موبایل معتبر نیست", 422, field="phone")

    as_user = db.execute(select(User).where(User.phone_e164 == phone)).scalar_one_or_none()
    if as_user is not None:
        return error_response(
            "APPLICANT_EXISTS_AS_USER",
            "این شماره قبلاً حساب کاربری ساخته است",
            409,
            details={"existing_user_id": str(as_user.id)},
        )

    duplicate = db.execute(
        select(Applicant).where(Applicant.phone_e164 == phone)
    ).scalar_one_or_none()
    if duplicate is not None:
        return error_response(
            "DUPLICATE_APPLICANT",
            "متقاضی با این شماره قبلاً ثبت شده است",
            409,
            details={"existing_applicant_id": str(duplicate.id)},
        )

    applicant = Applicant(
        full_name=body.full_name.strip(),
        phone_e164=phone,
        notes=body.notes,
        created_by=user.id,
    )
    db.add(applicant)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="applicant.create",
        outcome="allowed",
        resource_type="applicant",
        resource_id=applicant.id,
        request_id=request_id_var.get(),
    )
    return JSONResponse(status_code=201, content=envelope(data=_applicant_data(applicant)))


@router.get("/applicants")
def list_applicants(
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("applicants.read")),
    db: Session = Depends(get_db),
):
    stmt = select(Applicant)
    count_stmt = select(func.count()).select_from(Applicant)
    if q and q.strip():
        like = f"%{q.strip()}%"
        cond = or_(Applicant.full_name.ilike(like), Applicant.phone_e164.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = db.execute(count_stmt).scalar_one()
    rows = (
        db.execute(stmt.order_by(Applicant.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return envelope(
        data=[_applicant_data(a) for a in rows],
        extra_meta={"total": total, "limit": limit, "offset": offset},
    )


@router.get("/applicants/{applicant_id}")
def get_applicant(
    applicant_id: uuid.UUID,
    user: User = Depends(require_permission("applicants.read")),
    db: Session = Depends(get_db),
):
    applicant = db.get(Applicant, applicant_id)
    if applicant is None:
        return error_response("APPLICANT_NOT_FOUND", "متقاضی یافت نشد", 404)
    return envelope(data=_applicant_data(applicant))
