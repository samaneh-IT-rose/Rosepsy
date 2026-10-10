import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.consents import Consent, ConsentVersion
from app.models.core import User
from app.services.authz import write_audit

router = APIRouter(tags=["consents"])

CONSENT_KINDS = ("treatment", "psych_test", "marketing", "data_sharing")


class ConsentIn(BaseModel):
    kind: str = Field(min_length=2, max_length=32)
    channel: str = Field(default="web", pattern=r"^[a-z_]{2,20}$")


class VersionIn(BaseModel):
    kind: str = Field(min_length=2, max_length=32)
    title_fa: str = Field(min_length=2, max_length=150)
    text_fa: str = Field(min_length=10, max_length=5000)


def _latest_version(db: Session, kind: str) -> ConsentVersion | None:
    return db.execute(
        select(ConsentVersion)
        .where(ConsentVersion.kind == kind)
        .order_by(ConsentVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _version_data(v: ConsentVersion) -> dict:
    return {
        "id": str(v.id),
        "kind": v.kind,
        "version": v.version,
        "title_fa": v.title_fa,
        "text_fa": v.text_fa,
    }


def _consent_data(db: Session, c: Consent) -> dict:
    v = db.get(ConsentVersion, c.version_id)
    return {
        "id": str(c.id),
        "kind": c.kind,
        "channel": c.channel,
        "granted_at": c.granted_at.isoformat(),
        "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
        "active": c.revoked_at is None,
        "version": _version_data(v) if v else None,
    }


@router.post("/consents", status_code=201)
def grant_consent(
    body: ConsentIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Grant one consent kind against its latest immutable version (B41)."""
    if body.kind not in CONSENT_KINDS:
        return error_response("CONSENT_KIND_NOT_FOUND", "نوع رضایت شناخته‌شده نیست", 404)
    version = _latest_version(db, body.kind)
    if version is None:
        return error_response(
            "CONSENT_KIND_NOT_FOUND", "برای این نوع رضایت نسخه‌ای تعریف نشده است", 404
        )
    dup = db.execute(
        select(Consent).where(
            Consent.user_id == user.id,
            Consent.kind == body.kind,
            Consent.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if dup is not None:
        return error_response("CONSENT_ALREADY_ACTIVE", "رضایت فعال برای این نوع وجود دارد", 409)

    consent = Consent(
        user_id=user.id,
        kind=body.kind,
        version_id=version.id,
        channel=body.channel,
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "-")[:255],
    )
    db.add(consent)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="consent.grant",
        outcome="allowed",
        resource_type="consent",
        resource_id=consent.id,
        request_id=request_id_var.get(),
        detail={"kind": body.kind, "version": version.version},
    )
    return envelope(data=_consent_data(db, consent))


@router.get("/consents")
def my_consents(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Own history with version text and dates (B41 acceptance)."""
    rows = (
        db.execute(
            select(Consent)
            .where(Consent.user_id == user.id)
            .order_by(Consent.granted_at.desc())
        )
        .scalars()
        .all()
    )
    return envelope(data=[_consent_data(db, c) for c in rows])


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(
    consent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke: cuts future effect, keeps history (B41). Owner only."""
    c = db.get(Consent, consent_id)
    if c is None or c.user_id != user.id:
        return error_response("CONSENT_NOT_FOUND", "رضایت یافت نشد", 404)
    if c.revoked_at is not None:
        return error_response("CONSENT_ALREADY_REVOKED", "این رضایت قبلاً باطل شده است", 409)
    c.revoked_at = datetime.now(UTC)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="consent.revoke",
        outcome="allowed",
        resource_type="consent",
        resource_id=c.id,
        request_id=request_id_var.get(),
        detail={"kind": c.kind},
    )
    return envelope(
        data={"id": str(c.id), "active": False, "revoked_at": c.revoked_at.isoformat()}
    )


@router.post("/consent-versions", status_code=201)
def create_version(
    body: VersionIn,
    user: User = Depends(require_permission("consents.manage")),
    db: Session = Depends(get_db),
):
    """Publish a new immutable version; it becomes the active one for new grants."""
    if body.kind not in CONSENT_KINDS:
        return error_response("CONSENT_KIND_NOT_FOUND", "نوع رضایت شناخته‌شده نیست", 404)
    latest = _latest_version(db, body.kind)
    next_version = (latest.version + 1) if latest else 1
    v = ConsentVersion(
        kind=body.kind,
        version=next_version,
        title_fa=body.title_fa.strip(),
        text_fa=body.text_fa.strip(),
    )
    db.add(v)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="consent.version.create",
        outcome="allowed",
        resource_type="consent_version",
        resource_id=v.id,
        request_id=request_id_var.get(),
        detail={"kind": body.kind, "version": next_version},
    )
    return envelope(data=_version_data(v))
