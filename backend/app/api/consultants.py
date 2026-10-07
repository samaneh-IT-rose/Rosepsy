import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.catalog import Consultant, Credential, Specialty, VerificationReview
from app.models.core import User
from app.services.authz import grant_role, has_permission, write_audit

router = APIRouter(tags=["consultants"])


class ConsultantIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    specialty_id: uuid.UUID | None = None
    bio: str | None = Field(default=None, max_length=2000)
    user_id: uuid.UUID | None = None  # link to an existing user account


class CredentialIn(BaseModel):
    kind: str = Field(pattern=r"^(degree|license|certificate)$")
    title: str = Field(min_length=2, max_length=150)
    license_number: str = Field(min_length=1, max_length=64)
    issued_by: str | None = Field(default=None, max_length=150)
    issued_at: datetime | None = None
    expires_at: datetime | None = None


class ReviewIn(BaseModel):
    credential_id: uuid.UUID
    decision: str = Field(pattern=r"^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


def _is_eligible(db: Session, consultant: Consultant) -> bool:
    """approved status AND at least one verified, unexpired credential (spec B05)."""
    if consultant.status != "approved":
        return False
    now = datetime.now(UTC)
    stmt = (
        select(Credential.id)
        .where(
            Credential.consultant_id == consultant.id,
            Credential.status == "verified",
            or_(Credential.expires_at.is_(None), Credential.expires_at >= now),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _eligible_condition():
    now = datetime.now(UTC)
    return and_(
        Consultant.status == "approved",
        exists().where(
            and_(
                Credential.consultant_id == Consultant.id,
                Credential.status == "verified",
                or_(Credential.expires_at.is_(None), Credential.expires_at >= now),
            )
        ),
    )


@router.post("/consultants", status_code=201)
def create_consultant(
    body: ConsultantIn,
    user: User = Depends(require_permission("consultants.manage")),
    db: Session = Depends(get_db),
):
    if body.specialty_id is not None and db.get(Specialty, body.specialty_id) is None:
        return error_response("SPECIALTY_NOT_FOUND", "تخصص یافت نشد", 404)
    linked_user = None
    if body.user_id is not None:
        linked_user = db.get(User, body.user_id)
        if linked_user is None:
            return error_response("USER_NOT_FOUND", "کاربر مقصد یافت نشد", 404)
    c = Consultant(
        display_name=body.display_name.strip(),
        specialty_id=body.specialty_id,
        bio=body.bio,
        user_id=body.user_id,
    )
    db.add(c)
    db.commit()
    if linked_user is not None:
        grant_role(db, user_id=linked_user.id, role_name="consultant", granted_by=user.id)
    write_audit(
        db,
        actor_user_id=user.id,
        action="consultant.create",
        outcome="allowed",
        resource_type="consultant",
        resource_id=c.id,
        request_id=request_id_var.get(),
    )
    return envelope(
        data={"id": str(c.id), "status": c.status, "booking_eligible": False}
    )


@router.get("/consultants")
def list_consultants(
    include_all: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Default: booking-eligible consultants only (spec rule B05)."""
    if include_all:
        if not has_permission(db, user.id, "consultants.manage"):
            return error_response("FORBIDDEN", "دسترسی غیرمجاز است", 403)
        rows = db.execute(select(Consultant).order_by(Consultant.display_name)).scalars().all()
    else:
        rows = (
            db.execute(select(Consultant).where(_eligible_condition()))
            .scalars()
            .all()
        )
    return envelope(
        data=[
            {
                "id": str(c.id),
                "display_name": c.display_name,
                "specialty_id": str(c.specialty_id) if c.specialty_id else None,
                "status": c.status,
                "booking_eligible": _is_eligible(db, c),
            }
            for c in rows
        ]
    )


@router.post("/consultants/{consultant_id}/credentials", status_code=201)
def add_credential(
    consultant_id: uuid.UUID,
    body: CredentialIn,
    user: User = Depends(require_permission("consultants.manage")),
    db: Session = Depends(get_db),
):
    c = db.get(Consultant, consultant_id)
    if c is None:
        return error_response("CONSULTANT_NOT_FOUND", "مشاور یافت نشد", 404)
    dup = db.execute(
        select(Credential).where(
            Credential.consultant_id == consultant_id,
            Credential.license_number == body.license_number,
        )
    ).scalar_one_or_none()
    if dup is not None:
        return error_response("DUPLICATE_CREDENTIAL", "این شماره مجوز قبلاً ثبت شده است", 409)
    cred = Credential(
        consultant_id=consultant_id,
        kind=body.kind,
        title=body.title.strip(),
        license_number=body.license_number,
        issued_by=body.issued_by,
        issued_at=body.issued_at,
        expires_at=body.expires_at,
    )
    db.add(cred)
    db.commit()
    return envelope(data={"id": str(cred.id), "status": cred.status})


@router.post("/verification-reviews", status_code=201)
def create_review(
    body: ReviewIn,
    user: User = Depends(require_permission("consultants.review")),
    db: Session = Depends(get_db),
):
    cred = db.get(Credential, body.credential_id)
    if cred is None:
        return error_response("CREDENTIAL_NOT_FOUND", "مدرک یافت نشد", 404)
    if cred.status != "pending":
        return error_response("CREDENTIAL_ALREADY_REVIEWED", "این مدرک قبلاً بررسی شده است", 409)
    cred.status = "verified" if body.decision == "approved" else "rejected"
    review = VerificationReview(
        consultant_id=cred.consultant_id,
        credential_id=cred.id,
        reviewer_id=user.id,
        decision=body.decision,
        note=body.note,
    )
    db.add(review)
    consultant = db.get(Consultant, cred.consultant_id)
    if body.decision == "approved" and consultant.status == "pending_review":
        consultant.status = "approved"
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="consultant.review",
        outcome="allowed",
        resource_type="consultant",
        resource_id=consultant.id,
        request_id=request_id_var.get(),
        detail={"decision": body.decision, "credential_id": str(cred.id)},
    )
    return envelope(
        data={
            "consultant_id": str(consultant.id),
            "consultant_status": consultant.status,
            "booking_eligible": _is_eligible(db, consultant),
        }
    )
