import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.catalog import Service, Specialty
from app.models.core import User
from app.services.authz import write_audit

router = APIRouter(tags=["catalog"])


class SpecialtyIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    description: str | None = Field(default=None, max_length=500)


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    specialty_id: uuid.UUID | None = None
    duration_minutes: int = Field(gt=0, le=600)
    session_type: str = Field(default="in_person", pattern=r"^(in_person|online)$")
    is_active: bool = True


class ServicePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    duration_minutes: int | None = Field(default=None, gt=0, le=600)
    is_active: bool | None = None


@router.post("/specialties", status_code=201)
def create_specialty(
    body: SpecialtyIn,
    user: User = Depends(require_permission("services.manage")),
    db: Session = Depends(get_db),
):
    dup = db.execute(
        select(Specialty).where(Specialty.slug == body.slug)
    ).scalar_one_or_none()
    if dup is not None:
        return error_response("DUPLICATE_SLUG", "این slug قبلاً ثبت شده است", 409)
    sp = Specialty(name=body.name.strip(), slug=body.slug, description=body.description)
    db.add(sp)
    db.commit()
    return envelope(data={"id": str(sp.id), "name": sp.name, "slug": sp.slug})


@router.get("/specialties")
def list_specialties(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = (
        db.execute(
            select(Specialty).where(Specialty.is_active.is_(True)).order_by(Specialty.name)
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[{"id": str(s.id), "name": s.name, "slug": s.slug} for s in rows]
    )


@router.post("/services", status_code=201)
def create_service(
    body: ServiceIn,
    user: User = Depends(require_permission("services.manage")),
    db: Session = Depends(get_db),
):
    if body.specialty_id is not None:
        sp = db.get(Specialty, body.specialty_id)
        if sp is None:
            return error_response("SPECIALTY_NOT_FOUND", "تخصص یافت نشد", 404)
    svc = Service(
        name=body.name.strip(),
        specialty_id=body.specialty_id,
        duration_minutes=body.duration_minutes,
        session_type=body.session_type,
        is_active=body.is_active,
    )
    db.add(svc)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="service.create",
        outcome="allowed",
        resource_type="service",
        resource_id=svc.id,
        request_id=request_id_var.get(),
    )
    return envelope(
        data={
            "id": str(svc.id),
            "name": svc.name,
            "duration_minutes": svc.duration_minutes,
            "session_type": svc.session_type,
            "is_active": svc.is_active,
        }
    )


@router.get("/services")
def list_services(
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active services by default; inactive only for services.manage holders."""
    stmt = select(Service)
    if include_inactive:
        from app.services.authz import has_permission

        if not has_permission(db, user.id, "services.manage"):
            return error_response("FORBIDDEN", "دسترسی غیرمجاز است", 403)
    else:
        stmt = stmt.where(Service.is_active.is_(True))
    rows = db.execute(stmt.order_by(Service.name)).scalars().all()
    return envelope(
        data=[
            {
                "id": str(s.id),
                "name": s.name,
                "specialty_id": str(s.specialty_id) if s.specialty_id else None,
                "duration_minutes": s.duration_minutes,
                "session_type": s.session_type,
                "is_active": s.is_active,
            }
            for s in rows
        ]
    )


@router.patch("/services/{service_id}")
def patch_service(
    service_id: uuid.UUID,
    body: ServicePatchIn,
    user: User = Depends(require_permission("services.manage")),
    db: Session = Depends(get_db),
):
    svc = db.get(Service, service_id)
    if svc is None:
        return error_response("SERVICE_NOT_FOUND", "خدمت یافت نشد", 404)
    if body.name is not None:
        svc.name = body.name.strip()
    if body.duration_minutes is not None:
        svc.duration_minutes = body.duration_minutes
    if body.is_active is not None:
        svc.is_active = body.is_active
    db.commit()
    return envelope(data={"id": str(svc.id), "is_active": svc.is_active})
