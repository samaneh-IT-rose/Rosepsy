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
from app.models.catalog import Service
from app.models.core import User
from app.models.org import Branch, BranchServiceOffering, Clinic
from app.services.authz import scoped_branch_ids, write_audit

router = APIRouter(tags=["clinics"])


class ClinicIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    description: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=20)
    website: str | None = Field(default=None, max_length=200)


class BranchIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    province: str | None = Field(default=None, max_length=60)
    city: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=300)
    postal_code: str | None = Field(default=None, max_length=10)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    working_hours: dict | None = None


class BranchPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    city: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    status: str | None = Field(default=None, pattern=r"^(draft|published|archived)$")
    working_hours: dict | None = None


class OfferingsIn(BaseModel):
    service_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


@router.post("/clinics", status_code=201)
def create_clinic(
    body: ClinicIn,
    user: User = Depends(require_permission("clinics.manage")),
    db: Session = Depends(get_db),
):
    dup = db.execute(select(Clinic).where(Clinic.slug == body.slug)).scalar_one_or_none()
    if dup is not None:
        return error_response("DUPLICATE_SLUG", "این slug قبلاً ثبت شده است", 409)
    c = Clinic(
        name=body.name.strip(), slug=body.slug, description=body.description,
        phone=body.phone, website=body.website,
    )
    db.add(c)
    db.commit()
    return envelope(data={"id": str(c.id), "slug": c.slug})


@router.get("/clinics")
def list_clinics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Clinic).where(Clinic.is_active.is_(True))).scalars().all()
    return envelope(
        data=[{"id": str(c.id), "name": c.name, "slug": c.slug} for c in rows]
    )


@router.post("/clinics/{clinic_id}/branches", status_code=201)
def create_branch(
    clinic_id: uuid.UUID,
    body: BranchIn,
    user: User = Depends(require_permission("clinics.manage")),
    db: Session = Depends(get_db),
):
    if db.get(Clinic, clinic_id) is None:
        return error_response("CLINIC_NOT_FOUND", "مرکز یافت نشد", 404)
    dup = db.execute(select(Branch).where(Branch.slug == body.slug)).scalar_one_or_none()
    if dup is not None:
        return error_response("DUPLICATE_SLUG", "این slug قبلاً ثبت شده است", 409)
    b = Branch(
        clinic_id=clinic_id, name=body.name.strip(), slug=body.slug,
        province=body.province, city=body.city, address=body.address,
        postal_code=body.postal_code, lat=body.lat, lon=body.lon,
        working_hours=body.working_hours, status="draft",
    )
    db.add(b)
    db.commit()
    return envelope(data={"id": str(b.id), "status": b.status})


@router.get("/clinics/{clinic_id}/branches")
def list_branches(
    clinic_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(select(Branch).where(Branch.clinic_id == clinic_id))
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(b.id),
                "name": b.name,
                "slug": b.slug,
                "city": b.city,
                "status": b.status,
            }
            for b in rows
        ]
    )


@router.patch("/branches/{branch_id}")
def update_branch(
    branch_id: uuid.UUID,
    body: BranchPatchIn,
    user: User = Depends(require_permission("branches.manage")),
    db: Session = Depends(get_db),
):
    """Branch edit with operational branch scope (spec s.12 ABAC light)."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        return error_response("BRANCH_NOT_FOUND", "شعبه یافت نشد", 404)
    scope = scoped_branch_ids(db, user.id, "branches.manage")
    if scope is not None and branch.id not in scope:
        write_audit(
            db,
            actor_user_id=user.id,
            action="branches.manage:scope",
            outcome="denied",
            resource_type="branch",
            resource_id=branch.id,
            request_id=request_id_var.get(),
        )
        return error_response("FORBIDDEN", "دسترسی شما به این شعبه مجاز نیست", 403)
    for field in ("name", "city", "address", "lat", "lon", "status", "working_hours"):
        value = getattr(body, field)
        if value is not None:
            setattr(branch, field, value)
    db.commit()
    return envelope(data={"id": str(branch.id), "status": branch.status})


@router.put("/branches/{branch_id}/services")
def set_branch_services(
    branch_id: uuid.UUID,
    body: OfferingsIn,
    user: User = Depends(require_permission("clinics.manage")),
    db: Session = Depends(get_db),
):
    branch = db.get(Branch, branch_id)
    if branch is None:
        return error_response("BRANCH_NOT_FOUND", "شعبه یافت نشد", 404)
    found = (
        db.execute(select(Service).where(Service.id.in_(body.service_ids)))
        .scalars()
        .all()
    )
    if len(found) != len(set(body.service_ids)):
        return error_response("SERVICE_NOT_FOUND", "یک یا چند خدمت یافت نشد", 404)
    current = {
        o.service_id: o
        for o in db.execute(
            select(BranchServiceOffering).where(BranchServiceOffering.branch_id == branch_id)
        )
        .scalars()
        .all()
    }
    wanted = set(body.service_ids)
    for sid in wanted - set(current):
        db.add(BranchServiceOffering(branch_id=branch_id, service_id=sid))
    for sid, offering in current.items():
        if sid not in wanted:
            db.delete(offering)
    db.commit()
    return envelope(data={"branch_id": str(branch_id), "service_count": len(wanted)})


@router.get("/branches/{branch_id}/services")
def branch_services(
    branch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Only services actually offered AND active at this branch (B31 acceptance)."""
    rows = (
        db.execute(
            select(Service)
            .join(BranchServiceOffering, BranchServiceOffering.service_id == Service.id)
            .where(
                BranchServiceOffering.branch_id == branch_id,
                BranchServiceOffering.is_active.is_(True),
                Service.is_active.is_(True),
            )
            .order_by(Service.name)
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(s.id),
                "name": s.name,
                "duration_minutes": s.duration_minutes,
                "session_type": s.session_type,
            }
            for s in rows
        ]
    )


@router.get("/public/branches")
def public_branches(city: str | None = None, db: Session = Depends(get_db)):
    """Published branches only; no auth (unpublished are never public - B31)."""
    stmt = select(Branch).where(Branch.status == "published")
    if city and city.strip():
        stmt = stmt.where(Branch.city.ilike(f"%{city.strip()}%"))
    rows = db.execute(stmt.order_by(Branch.name)).scalars().all()
    return envelope(
        data=[
            {
                "id": str(b.id),
                "name": b.name,
                "city": b.city,
                "province": b.province,
                "lat": float(b.lat),
                "lon": float(b.lon),
            }
            for b in rows
        ]
    )
