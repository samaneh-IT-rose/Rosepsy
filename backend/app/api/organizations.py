"""Organizations API (B21): contracts, members, validity."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.finance import (
    Organization,
    OrganizationContract,
    OrganizationMember,
)
from app.services.authz import write_audit
from app.services.organizations import is_active_member, org_data

router = APIRouter(tags=["organizations"])


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    national_id: str = Field(min_length=4, max_length=20)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=20)


class ContractIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    share_percent: float = Field(ge=0, le=100)
    valid_from: datetime
    valid_to: datetime | None = None


class MemberIn(BaseModel):
    user_id: uuid.UUID
    valid_days: int = Field(default=365, ge=1, le=3650)


@router.post("/organizations", status_code=201)
def create_organization(
    body: OrganizationIn,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    exists = db.execute(
        select(Organization).where(Organization.national_id == body.national_id)
    ).scalar_one_or_none()
    if exists is not None:
        return error_response("ORGANIZATION_EXISTS", "سازمانی با این شناسه ثبت شده است", 409)
    org = Organization(
        name=body.name,
        national_id=body.national_id,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
    )
    db.add(org)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="organization.create",
        outcome="allowed",
        resource_type="organization",
        resource_id=org.id,
    )
    return envelope(data=org_data(db, org))


@router.get("/organizations")
def list_organizations(
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Organization).order_by(Organization.created_at.desc()).limit(200)
    ).scalars().all()
    return envelope(data=[org_data(db, o) for o in rows])


@router.get("/organizations/{org_id}")
def get_organization(
    org_id: uuid.UUID,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if org is None:
        return error_response("ORGANIZATION_NOT_FOUND", "سازمان یافت نشد", 404)
    return envelope(data=org_data(db, org, include_members=True))


@router.post("/organizations/{org_id}/contracts", status_code=201)
def add_contract(
    org_id: uuid.UUID,
    body: ContractIn,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if org is None:
        return error_response("ORGANIZATION_NOT_FOUND", "سازمان یافت نشد", 404)
    if body.valid_to is not None and body.valid_to <= body.valid_from:
        return error_response("CONTRACT_WINDOW_INVALID", "بازه قرارداد نامعتبر است", 422)
    contract = OrganizationContract(
        organization_id=org_id,
        title=body.title,
        share_percent=body.share_percent,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
    )
    db.add(contract)
    db.commit()
    return envelope(
        data={
            "id": str(contract.id),
            "title": contract.title,
            "share_percent": float(contract.share_percent),
        }
    )


@router.post("/organizations/{org_id}/members", status_code=201)
def add_member(
    org_id: uuid.UUID,
    body: MemberIn,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if org is None:
        return error_response("ORGANIZATION_NOT_FOUND", "سازمان یافت نشد", 404)
    if not org.is_active:
        return error_response("ORGANIZATION_INACTIVE", "سازمان غیرفعال است", 409)
    if is_active_member(db, body.user_id) is not None:
        return error_response(
            "MEMBER_ALREADY_ACTIVE", "کاربر عضو فعال یک سازمان دیگر است", 409
        )
    member = OrganizationMember(
        organization_id=org_id,
        user_id=body.user_id,
        valid_from=datetime.now(UTC),
        valid_to=datetime.now(UTC) + timedelta(days=body.valid_days),
        created_by=user.id,
    )
    db.add(member)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="organization.member_add",
        outcome="allowed",
        resource_type="organization_member",
        resource_id=member.id,
        detail={"org_id": str(org_id), "user_id": str(body.user_id)},
    )
    return envelope(
        data={
            "id": str(member.id),
            "user_id": str(member.user_id),
            "valid_from": member.valid_from.isoformat(),
            "valid_to": member.valid_to.isoformat(),
        }
    )


@router.delete("/organizations/{org_id}/members/{user_id}")
def end_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    member = is_active_member(db, user_id)
    if member is None or member.organization_id != org_id:
        return error_response("MEMBERSHIP_NOT_FOUND", "عضویت فعالی یافت نشد", 404)
    member.valid_to = datetime.now(UTC)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="organization.member_end",
        outcome="allowed",
        resource_type="organization_member",
        resource_id=member.id,
    )
    return envelope(data={"user_id": str(user_id), "ended": True})
