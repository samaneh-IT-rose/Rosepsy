"""Organization service (B21): membership validity checked at service time.

Rule from the spec: membership must be valid WHEN the service is delivered;
an expired membership never grants benefits retroactively, and the
organization never gains access to clinical notes (no clinical linkage here
by design).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import Organization, OrganizationContract, OrganizationMember


def is_active_member(
    db: Session, user_id: uuid.UUID, at: datetime | None = None
) -> OrganizationMember | None:
    """Return the active membership row for the user at time `at` (now by default)."""
    now = at or datetime.now(UTC)
    return db.execute(
        select(OrganizationMember)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.valid_from <= now,
            (OrganizationMember.valid_to.is_(None)) | (OrganizationMember.valid_to >= now),
        )
        .order_by(OrganizationMember.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()


def active_contract(
    db: Session, organization_id: uuid.UUID, at: datetime | None = None
) -> OrganizationContract | None:
    now = at or datetime.now(UTC)
    return db.execute(
        select(OrganizationContract)
        .where(
            OrganizationContract.organization_id == organization_id,
            OrganizationContract.is_active.is_(True),
            OrganizationContract.valid_from <= now,
            (OrganizationContract.valid_to.is_(None)) | (OrganizationContract.valid_to >= now),
        )
        .order_by(OrganizationContract.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()


def org_data(
    db: Session, org: Organization, include_members: bool = False
) -> dict:
    data = {
        "id": str(org.id),
        "name": org.name,
        "national_id": org.national_id,
        "contact_name": org.contact_name,
        "contact_phone": org.contact_phone,
        "is_active": org.is_active,
        "created_at": org.created_at.isoformat(),
    }
    if include_members:
        members = db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id
            )
        ).scalars().all()
        data["members"] = [
            {
                "id": str(m.id),
                "user_id": str(m.user_id),
                "valid_from": m.valid_from.isoformat(),
                "valid_to": m.valid_to.isoformat() if m.valid_to else None,
            }
            for m in members
        ]
        contracts = db.execute(
            select(OrganizationContract).where(
                OrganizationContract.organization_id == org.id
            )
        ).scalars().all()
        data["contracts"] = [
            {
                "id": str(c.id),
                "title": c.title,
                "share_percent": float(c.share_percent),
                "valid_from": c.valid_from.isoformat(),
                "valid_to": c.valid_to.isoformat() if c.valid_to else None,
                "is_active": c.is_active,
            }
            for c in contracts
        ]
    return data
