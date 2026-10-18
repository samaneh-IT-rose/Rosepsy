"""Admin panel API (B42) — alignment with «سند ساختاریافته شناسایی صفحات».

Endpoints backing the pages identified by the document:
- dashboard (doc s.3)        → GET  /admin/dashboard
- regional filters (s.4.1)   → GET  /admin/provinces, /admin/cities
- users table (s.4)          → GET  /admin/users, PATCH /admin/users/{id}
- ورود (s.4.5)               → POST /admin/users/{id}/switch-session
- profile/services (s.5)     → GET  /admin/users/{id}, GET /admin/event-details/{code}
- centers (s.6)              → GET/POST/PATCH /admin/centers*, /admin/center-groups
- reports cards (s.7)        → GET  /admin/reports
- event reports (s.7.2)      → GET  /admin/reports/events
- consultant report (s.8)    → GET  /admin/reports/consultants
- activity log (s.3.1.2 #27) → GET  /admin/logs

Conventions: standard envelope, RBAC via require_permission, audit for every
write/sensitive read, Gregorian UTC timestamps (Jalali rendering is UI-only).
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.config import settings
from app.core.db import get_db
from app.core.security import generate_session_token, hash_secret
from app.models.admin import City, ClinicGroup, Referral
from app.models.audit import AuditLog
from app.models.booking import Appointment
from app.models.catalog import Consultant, Credential, Service
from app.models.core import AuthSession, Profile, User
from app.models.org import Branch, Clinic
from app.services import admin_data
from app.services.authz import write_access_event, write_audit

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_LENGTHS = (10, 25, 50, 100, -1)  # doc s.4.5 «نمایش»: ۱۰/۲۵/۵۰/۱۰۰/همه

GENDER_FA = {"male": "مرد", "female": "زن"}
MARITAL_FA = {"single": "مجرد", "married": "متأهل"}

USERS_COLUMNS = [  # doc s.4.2 — 11 columns, exactly in order
    "کد",
    "نام کاربری",
    "نام و نام خانوادگی",
    "نام پدر",
    "جنسیت",
    "شماره همراه",
    "استان",
    "تحصیلات",
    "تاریخ تولد",
    "تاریخ ثبت‌نام",
    "آخرین ورود",
]

SERVICES_COLUMNS = [  # doc s.5.3 — 12 columns, exactly in order
    "شناسه",
    "شناسه ارجاع",
    "سرویس",
    "قرارداد",
    "تعرفه کاربر",
    "کیس حاد",
    "مشاور",
    "مرکز",
    "وضعیت",
    "تاریخ شروع",
    "تاریخ پایان",
    "بیشتر",
]

CENTERS_COLUMNS = [  # doc s.6.4 — 5 columns
    "نام کلینیک",
    "استان",
    "شهر",
    "وضعیت کلینیک",
    "جزئیات",
]

EVENT_KIND_MAP = {  # doc s.7.2 — the four event-report cards
    "individual": ("done", "undone"),
    "group": ("done", "undone"),
}


def _province_name(code: int | None) -> str | None:
    if code is None:
        return None
    for c, name in admin_data.PROVINCES:
        if c == code:
            return name
    return None


def _age_from(birth: date | None) -> int | None:
    """Age is always COMPUTED from birth_date (resolves doc s.11 item ۶)."""
    if birth is None:
        return None
    today = date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def _paging(start: int, length: int, total: int) -> tuple[int, int]:
    if length == -1:
        return 0, total
    return start, length


# ──────────────────────────── dashboard (doc s.3) ────────────────────────────


@router.get("/dashboard")
def dashboard(
    user: User = Depends(require_permission("admin.panel")),
    db: Session = Depends(get_db),
):
    stats = {
        "users": db.execute(select(func.count()).select_from(User)).scalar_one(),
        "centers": db.execute(select(func.count()).select_from(Branch)).scalar_one(),
        "consultants": db.execute(select(func.count()).select_from(Consultant)).scalar_one(),
        "referrals": db.execute(select(func.count()).select_from(Referral)).scalar_one(),
    }
    return envelope(
        data={
            "identity": admin_data.DASHBOARD_IDENTITY,
            "shortcuts": admin_data.SHORTCUTS,
            "menus": admin_data.MENUS,
            "user_section": admin_data.USER_SECTION,
            "stats": stats,
        }
    )


# ───────────────────── regional reference (doc s.4.1 / s.9) ─────────────────────


@router.get("/provinces")
def provinces(user: User = Depends(require_permission("admin.panel"))):
    return envelope(data=[{"code": c, "name": n} for c, n in admin_data.PROVINCES])


@router.get("/cities")
def cities(
    province_code: int = Query(ge=1, le=31),
    user: User = Depends(require_permission("admin.panel")),
    db: Session = Depends(get_db),
):
    """Dynamic «شهرستان» options per province (doc s.4.1)."""
    rows = db.execute(
        select(City).where(City.province_code == province_code).order_by(City.name)
    ).scalars().all()
    return envelope(data=[{"id": str(c.id), "name": c.name} for c in rows])


# ──────────────────────── users management (doc s.4) ────────────────────────


def _user_query(db: Session, province: int | None, city: str | None, q: str | None):
    stmt = (
        select(User, Profile)
        .outerjoin(Profile, Profile.user_id == User.id)
        .order_by(User.created_at.desc())
    )
    if province is not None and province != 0:  # 0 = «کل کشور»
        stmt = stmt.where(Profile.province_code == province)
    if city and city.strip():
        stmt = stmt.where(Profile.city.ilike(f"%{city.strip()}%"))
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Profile.first_name.ilike(needle),
                Profile.last_name.ilike(needle),
                Profile.username.ilike(needle),
                Profile.national_id.ilike(needle),
                User.phone_e164.ilike(needle),
            )
        )
    return stmt


def _user_row(u: User, p: Profile | None) -> dict:
    full_name = f"{p.first_name} {p.last_name}".strip() if p else ""
    last_login = u.last_login_at.isoformat() if u.last_login_at else None
    return {
        "id": str(u.id),
        "code": p.code if p else None,
        "username": p.username if p else None,
        "full_name": full_name or None,
        "avatar_url": p.avatar_url if p else None,
        "father_name": p.father_name if p else None,
        "gender": p.gender if p else None,
        "gender_fa": GENDER_FA.get(p.gender) if p and p.gender else None,
        "mobile": u.phone_e164,
        "province_code": p.province_code if p else None,
        "province_fa": _province_name(p.province_code) if p else None,
        "education": p.education if p else None,
        "birth_date": p.birth_date.isoformat() if p and p.birth_date else None,
        "registered_at": u.created_at.isoformat(),
        "last_login_at": last_login,
        # row-drop details (doc s.4.3)
        "details": {
            "username": p.username if p else None,
            "email": p.email if p else None,
            "address": p.address if p else None,
            "postal_code": p.postal_code if p else None,
            "registration_source": p.registration_source if p else None,
        },
    }


@router.get("/users")
def list_users(
    province: int | None = Query(default=None, ge=0, le=31),
    city: str | None = None,
    q: str | None = None,
    start: int = Query(default=0, ge=0),
    length: int = Query(default=10),
    user: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
):
    if length not in ALLOWED_LENGTHS:
        return error_response("INVALID_LENGTH", "طول صفحه مجاز نیست", 422, field="length")
    stmt = _user_query(db, province, city, q)
    total = db.execute(
        select(User.id).outerjoin(Profile, Profile.user_id == User.id)
    ).scalars().all()
    total_count = len(total)
    filtered = len(db.execute(stmt).all())
    offset, limit = _paging(start, length, filtered)
    if limit:
        stmt = stmt.offset(offset).limit(limit)
    rows = db.execute(stmt).all()
    return envelope(
        data={
            "records_total": total_count,
            "records_filtered": filtered,
            "offset": offset,
            "columns": USERS_COLUMNS,
            "rows": [_user_row(u, p) for u, p in rows],
        }
    )


class ProfileEditIn(BaseModel):
    """Editable identity fields (doc s.5.2 — resolved: fields are editable)."""

    username: str | None = Field(default=None, max_length=64)
    national_id: str | None = Field(default=None, pattern=r"^\d{10}$")
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    father_name: str | None = Field(default=None, max_length=80)
    gender: str | None = Field(default=None, pattern=r"^(male|female)$")
    education: str | None = Field(default=None, max_length=40)
    marital_status: str | None = Field(default=None, pattern=r"^(single|married)$")
    birth_date: date | None = None
    province_code: int | None = Field(default=None, ge=1, le=31)
    city: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=300)
    postal_code: str | None = Field(default=None, pattern=r"^\d{5,10}$")
    email: str | None = Field(default=None, max_length=120)
    registration_source: str | None = Field(default=None, max_length=80)


@router.patch("/users/{user_id}")
def edit_user(
    user_id: uuid.UUID,
    body: ProfileEditIn,
    user: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    profile = db.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)
    changed = []
    for field in (
        "username",
        "national_id",
        "first_name",
        "last_name",
        "father_name",
        "gender",
        "education",
        "marital_status",
        "birth_date",
        "province_code",
        "city",
        "address",
        "postal_code",
        "email",
        "registration_source",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(profile, field, value)
            changed.append(field)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="users.manage:edit",
        outcome="ok",
        resource_type="user",
        resource_id=user_id,
        detail={"changed": changed},
        ip=None,
    )
    return envelope(data={"id": str(user_id), "changed": changed})


@router.post("/users/{user_id}/switch-session")
def switch_session(
    user_id: uuid.UUID,
    request_user: User = Depends(require_permission("users.switch_session")),
    db: Session = Depends(get_db),
):
    """«ورود» به حساب کاربر (doc s.4.5) — with mandatory audit (doc s.11 item ۱۵)."""
    target = db.get(User, user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    if target.status != "active":
        return error_response("USER_INACTIVE", "حساب کاربر فعال نیست", 409)
    from datetime import timedelta

    token = generate_session_token()
    now = datetime.now(UTC)
    ttl = timedelta(seconds=settings.AUTH_SESSION_TTL_SECONDS)
    db.add(
        AuthSession(
            user_id=target.id,
            token_hash=hash_secret(token),
            expires_at=now + ttl,
            ip=None,
            user_agent="admin-switch-session",
        )
    )
    db.commit()
    write_audit(
        db,
        actor_user_id=request_user.id,
        action="users.switch_session",
        outcome="ok",
        resource_type="user",
        resource_id=target.id,
        detail={"target_phone": target.phone_e164},
        ip=None,
    )
    return envelope(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_at": (now + ttl).isoformat(),
            "user": {"id": str(target.id), "phone": target.phone_e164},
        }
    )


# ─────────────────── user profile + services (doc s.5) ───────────────────


def _service_rows(db: Session, user_id: uuid.UUID) -> list[dict]:
    stmt = (
        select(Appointment, Referral, Service, Consultant, Branch)
        .outerjoin(Referral, Referral.id == Appointment.referral_id)
        .outerjoin(Service, Service.id == Appointment.service_id)
        .outerjoin(Consultant, Consultant.id == Appointment.consultant_id)
        .outerjoin(Branch, Branch.id == Appointment.branch_id)
        .where(Appointment.user_id == user_id)
        .order_by(Appointment.start_at.desc())
    )
    rows = db.execute(stmt).all()
    out = []
    for appt, ref, service, consultant, branch in rows:
        referral_code = ref.code if ref else None
        contract = ref.contract_title if ref else None
        tariff = ref.user_tariff if ref else None
        status_ref = ref.status if ref else None
        out.append(
            {
                "id": str(appt.id),
                "code": appt.code,
                "referral_code": referral_code,
                "service": service.name if service else None,
                "session_type": service.session_type if service else None,
                "contract": contract,
                "user_tariff": tariff,
                "acute": appt.acute_status,
                "acute_fa": admin_data.ACUTE_STATUS_FA.get(appt.acute_status or ""),
                "consultant": consultant.display_name if consultant else None,
                "branch": branch.name if branch else None,
                "status": appt.status,
                "status_fa": admin_data.APPOINTMENT_STATUS_FA.get(appt.status, appt.status),
                "referral_status_fa": admin_data.REFERRAL_STATUS_FA.get(
                    status_ref or "", status_ref
                ),
                "start_at": appt.start_at.isoformat(),
                "end_at": appt.end_at.isoformat(),
                "details_options": admin_data.EVENT_DETAILS_OPTIONS,
            }
        )
    return out


@router.get("/users/{user_id}")
def user_profile(
    user_id: uuid.UUID,
    user: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
):
    """پرونده کاربر (doc s.5): personal info + services table + «بیشتر» options."""
    target = db.get(User, user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    p = db.get(Profile, user_id)
    write_access_event(
        db,
        actor_user_id=user.id,
        subject_user_id=target.id,
        action="admin.profile.read",
        allowed=True,
        resource_type="profile",
        resource_id=target.id,
    )
    personal = {
        "id": str(target.id),
        "code": p.code if p else None,
        "username": p.username if p else None,
        "national_id": p.national_id if p else None,
        "first_name": p.first_name if p else None,
        "last_name": p.last_name if p else None,
        "father_name": p.father_name if p else None,
        "mobile": target.phone_e164,
        "education": p.education if p else None,
        "province": _province_name(p.province_code) if p else None,
        "province_code": p.province_code if p else None,
        "city": p.city if p else None,
        "gender": p.gender if p else None,
        "gender_fa": GENDER_FA.get(p.gender) if p and p.gender else None,
        "marital_status": p.marital_status if p else None,
        "marital_status_fa": MARITAL_FA.get(p.marital_status)
        if p and p.marital_status
        else None,
        "birth_date": p.birth_date.isoformat() if p and p.birth_date else None,
        "age": _age_from(p.birth_date) if p else None,  # computed (doc s.11 item ۶)
        "address": p.address if p else None,
        "email": p.email if p else None,
        "postal_code": p.postal_code if p else None,
        "registration_source": p.registration_source if p else None,
        "registered_at": target.created_at.isoformat(),
        "last_login_at": target.last_login_at.isoformat() if target.last_login_at else None,
    }
    return envelope(
        data={
            "personal": personal,
            "services": {"columns": SERVICES_COLUMNS, "rows": _service_rows(db, user_id)},
        }
    )


@router.get("/event-details/{appointment_code}")
def event_details(
    appointment_code: int,
    kind: str = Query(default="0", pattern=r"^(0|EVENT|REFF)$"),
    user: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
):
    """«بیشتر» control (doc s.5.5): جزئیات / جزئیات جلسه / جزئیات ارجاع."""
    appt = db.execute(
        select(Appointment).where(Appointment.code == appointment_code)
    ).scalar_one_or_none()
    if appt is None:
        return error_response("EVENT_NOT_FOUND", "جلسه یافت نشد", 404)
    data: dict = {"appointment_code": appointment_code, "kind": kind}
    if kind in ("0", "EVENT"):
        service = db.get(Service, appt.service_id)
        consultant = db.get(Consultant, appt.consultant_id) if appt.consultant_id else None
        branch = db.get(Branch, appt.branch_id) if appt.branch_id else None
        data["event"] = {
            "code": appt.code,
            "service": service.name if service else None,
            "consultant": consultant.display_name if consultant else None,
            "branch": branch.name if branch else None,
            "status": appt.status,
            "status_fa": admin_data.APPOINTMENT_STATUS_FA.get(appt.status, appt.status),
            "acute_fa": admin_data.ACUTE_STATUS_FA.get(appt.acute_status or ""),
            "start_at": appt.start_at.isoformat(),
            "end_at": appt.end_at.isoformat(),
        }
    if kind in ("0", "REFF"):
        ref = db.get(Referral, appt.referral_id) if appt.referral_id else None
        data["referral"] = (
            {
                "code": ref.code,
                "contract": ref.contract_title,
                "user_tariff": ref.user_tariff,
                "status": ref.status,
                "status_fa": admin_data.REFERRAL_STATUS_FA.get(ref.status, ref.status),
                "source": ref.source,
                "created_at": ref.created_at.isoformat(),
            }
            if ref
            else None
        )
    return envelope(data=data)


# ──────────────────────── centers management (doc s.6) ────────────────────────


def _center_query(db: Session, province: int | None, city: str | None, activation: str | None):
    stmt = select(Branch).order_by(Branch.legacy_code.nulls_last(), Branch.name)
    if province is not None and province != 0:
        stmt = stmt.where(Branch.province == _province_name(province))
    if city and city.strip():
        stmt = stmt.where(Branch.city.ilike(f"%{city.strip()}%"))
    if activation == "1":  # doc s.6.3: فعال = 1
        stmt = stmt.where(Branch.status == "published")
    elif activation == "0":  # غیرفعال = 0 ; «همه» = all/empty (doc s.11 item ۵)
        stmt = stmt.where(Branch.status != "published")
    return stmt


def _center_row(b: Branch, group: ClinicGroup | None = None) -> dict:
    return {
        "id": str(b.id),
        "name": b.name,
        "province": b.province,
        "city": b.city,
        "status": b.status,
        "is_active": b.status == "published",
        "legacy_code": b.legacy_code,
        "address": b.address,
        "group": group.name if group else None,
        "clinic_id": str(b.clinic_id),
    }


@router.get("/centers")
def list_centers(
    province: int | None = Query(default=None, ge=0, le=31),
    city: str | None = None,
    activation: str | None = Query(default=None, pattern=r"^(all|1|0)$"),
    start: int = Query(default=0, ge=0),
    length: int = Query(default=100),
    user: User = Depends(require_permission("admin.panel")),
    db: Session = Depends(get_db),
):
    if length not in ALLOWED_LENGTHS:
        return error_response("INVALID_LENGTH", "طول صفحه مجاز نیست", 422, field="length")
    stmt = _center_query(db, province, city, activation)
    all_rows = db.execute(stmt).scalars().all()
    filtered = len(all_rows)
    total = db.execute(select(Branch)).scalars().all()
    offset, limit = _paging(start, length, filtered)
    page_rows = all_rows[offset : offset + limit] if limit else all_rows[offset:]
    return envelope(
        data={
            "records_total": len(total),
            "records_filtered": filtered,
            "offset": offset,
            "columns": CENTERS_COLUMNS,
            "rows": [_center_row(b) for b in page_rows],
        }
    )


@router.get("/centers/export")
def export_centers(
    province: int | None = Query(default=None, ge=0, le=31),
    city: str | None = None,
    activation: str | None = Query(default=None, pattern=r"^(all|1|0)$"),
    user: User = Depends(require_permission("admin.panel")),
    db: Session = Depends(get_db),
):
    """Excel-compatible CSV (UTF-8 BOM) covering ALL filtered rows
    (resolves doc s.11 item: «محدوده خروجی اکسل مشخص نیست»)."""
    rows = db.execute(_center_query(db, province, city, activation)).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["نام کلینیک", "استان", "شهر", "وضعیت کلینیک", "شناسه"])
    for b in rows:
        status_fa = "فعال" if b.status == "published" else "غیرفعال"
        writer.writerow(
            [b.name, b.province or "", b.city or "", status_fa, b.legacy_code or ""]
        )
    content = "\ufeff" + buf.getvalue()
    write_audit(
        db,
        actor_user_id=user.id,
        action="centers.export",
        outcome="ok",
        resource_type="branch",
        detail={"count": len(rows)},
        ip=None,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=centers.csv"},
    )


class CenterIn(BaseModel):
    """ایجاد کلینیک (doc s.6.2 addCenter)."""

    name: str = Field(min_length=2, max_length=150)
    province_code: int = Field(ge=1, le=31)
    city: str = Field(min_length=2, max_length=60)
    address: str | None = Field(default=None, max_length=300)
    group_id: uuid.UUID | None = None
    clinic_name: str | None = Field(default=None, max_length=150)


@router.post("/centers", status_code=201)
def create_center(
    body: CenterIn,
    user: User = Depends(require_permission("clinics.manage")),
    db: Session = Depends(get_db),
):
    if body.group_id is not None and db.get(ClinicGroup, body.group_id) is None:
        return error_response("GROUP_NOT_FOUND", "گروه یافت نشد", 404)
    clinic_name = body.clinic_name or "مجموعه راه زندگی رز سفید"
    clinic = db.execute(select(Clinic).where(Clinic.name == clinic_name)).scalar_one_or_none()
    if clinic is None:
        clinic = Clinic(name=clinic_name, slug=f"rose-{uuid.uuid4().hex[:10]}")
        db.add(clinic)
        db.flush()
    branch = Branch(
        clinic_id=clinic.id,
        name=body.name.strip(),
        slug=f"center-{uuid.uuid4().hex[:10]}",
        province=_province_name(body.province_code),
        city=body.city.strip(),
        address=body.address,
        lat=0,
        lon=0,
        status="published",
        clinic_group_id=body.group_id,
    )
    db.add(branch)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="centers.create",
        outcome="ok",
        resource_type="branch",
        resource_id=branch.id,
        ip=None,
    )
    return envelope(data=_center_row(branch))


class CenterPatchIn(BaseModel):
    is_active: bool
    name: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=300)


@router.patch("/centers/{branch_id}")
def update_center(
    branch_id: uuid.UUID,
    body: CenterPatchIn,
    user: User = Depends(require_permission("clinics.manage")),
    db: Session = Depends(get_db),
):
    branch = db.get(Branch, branch_id)
    if branch is None:
        return error_response("CENTER_NOT_FOUND", "مرکز یافت نشد", 404)
    if body.is_active:
        branch.status = "published"
    elif branch.status == "published":
        branch.status = "draft"  # غیرفعال
    for field in ("name", "city", "address"):
        value = getattr(body, field)
        if value is not None:
            setattr(branch, field, value)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="centers.update",
        outcome="ok",
        resource_type="branch",
        resource_id=branch.id,
        detail={"is_active": body.is_active},
        ip=None,
    )
    return envelope(data=_center_row(branch))


@router.get("/centers/{branch_id}")
def center_detail(
    branch_id: uuid.UUID,
    user: User = Depends(require_permission("admin.panel")),
    db: Session = Depends(get_db),
):
    """مشاهده (doc s.6.6 centerDetail)."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        return error_response("CENTER_NOT_FOUND", "مرکز یافت نشد", 404)
    group = db.get(ClinicGroup, branch.clinic_group_id) if branch.clinic_group_id else None
    clinic = db.get(Clinic, branch.clinic_id)
    data = _center_row(branch, group)
    data["clinic_name"] = clinic.name if clinic else None
    data["working_hours"] = branch.working_hours
    return envelope(data=data)


class CenterGroupIn(BaseModel):
    """گروه‌بندی کلینیک‌ها (doc s.6.2 addCenterCategory)."""

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)


@router.post("/center-groups", status_code=201)
def create_center_group(
    body: CenterGroupIn,
    user: User = Depends(require_permission("clinics.manage")),
    db: Session = Depends(get_db),
):
    dup = db.execute(
        select(ClinicGroup).where(ClinicGroup.name == body.name.strip())
    ).scalar_one_or_none()
    if dup is not None:
        return error_response("DUPLICATE_GROUP", "این گروه قبلاً ثبت شده است", 409)
    group = ClinicGroup(name=body.name.strip(), description=body.description, created_by=user.id)
    db.add(group)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="center-groups.create",
        outcome="ok",
        resource_type="clinic_group",
        resource_id=group.id,
        ip=None,
    )
    return envelope(data={"id": str(group.id), "name": group.name})


@router.get("/center-groups")
def list_center_groups(
    user: User = Depends(require_permission("admin.panel")),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(ClinicGroup).order_by(ClinicGroup.name)).scalars().all()
    return envelope(data=[{"id": str(g.id), "name": g.name} for g in rows])


# ───────────────────────── reports (doc s.7 / s.8) ─────────────────────────


@router.get("/reports")
def reports(user: User = Depends(require_permission("reports.read"))):
    """Reports landing page: 3 groups, 10 cards (doc s.7.2–7.4)."""
    return envelope(data={"groups": admin_data.REPORT_GROUPS})


@router.get("/reports/events")
def event_report(
    kind: str = Query(default="individual", pattern=r"^(individual|group)$"),
    state: str = Query(default="done", pattern=r"^(done|undone)$"),
    start: int = Query(default=0, ge=0),
    length: int = Query(default=25),
    user: User = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Backing report for the four event cards (doc s.7.2)."""
    stmt = (
        select(Appointment, Service, Consultant, Branch, Referral)
        .outerjoin(Service, Service.id == Appointment.service_id)
        .outerjoin(Consultant, Consultant.id == Appointment.consultant_id)
        .outerjoin(Branch, Branch.id == Appointment.branch_id)
        .outerjoin(Referral, Referral.id == Appointment.referral_id)
        .order_by(Appointment.start_at.desc())
    )
    if kind == "group":
        stmt = stmt.where(Service.session_type == "group")
    else:
        stmt = stmt.where(or_(Service.session_type.is_(None), Service.session_type != "group"))
    if state == "done":
        stmt = stmt.where(Appointment.status == "completed")
    else:
        stmt = stmt.where(
            Appointment.status.in_(("pending_payment", "confirmed", "in_progress"))
        )
    rows = db.execute(stmt).all()
    total = len(rows)
    offset, limit = _paging(start, length, total)
    page = rows[offset : offset + limit] if limit else rows[offset:]
    data_rows = []
    for appt, service, consultant, branch, ref in page:
        data_rows.append(
            {
                "code": appt.code,
                "service": service.name if service else None,
                "consultant": consultant.display_name if consultant else None,
                "branch": branch.name if branch else None,
                "referral_code": ref.code if ref else None,
                "status_fa": admin_data.APPOINTMENT_STATUS_FA.get(appt.status, appt.status),
                "start_at": appt.start_at.isoformat(),
                "end_at": appt.end_at.isoformat(),
            }
        )
    return envelope(data={"kind": kind, "state": state, "total": total, "rows": data_rows})


@router.get("/reports/consultants")
def consultant_report(
    group_by: str = Query(default="none", pattern=r"^(none|province|service)$"),
    format: str = Query(default="json", pattern=r"^(json|csv)$"),
    user: User = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """گزارش مشاوران و خدمات (doc s.8): identity + per-service rows + totals.

    group_by=province|service groups the service rows accordingly (doc s.8.5).
    """
    consultants = db.execute(select(Consultant).order_by(Consultant.display_name)).scalars().all()
    result = []
    row_no = 0
    for c in consultants:
        degree = db.execute(
            select(Credential)
            .where(Credential.consultant_id == c.id, Credential.kind == "degree")
            .order_by(Credential.created_at.desc())
        ).scalars().first()
        stmt = (
            select(Appointment, Branch, Service)
            .outerjoin(Branch, Branch.id == Appointment.branch_id)
            .outerjoin(Service, Service.id == Appointment.service_id)
            .where(Appointment.consultant_id == c.id)
        )
        pairs = db.execute(stmt).all()
        # group service rows
        grouped: dict[tuple, dict] = {}
        for appt, branch, service in pairs:
            if group_by == "province":
                key = (branch.province if branch else None,)
                label = {
                    "province": branch.province if branch else None,
                    "city": None,
                    "branch": None,
                    "service": None,
                }
            elif group_by == "service":
                key = (service.name if service else None,)
                label = {
                    "province": None,
                    "city": None,
                    "branch": None,
                    "service": service.name if service else None,
                }
            else:
                key = (branch.id if branch else None, service.id if service else None)
                label = {
                    "province": branch.province if branch else None,
                    "city": branch.city if branch else None,
                    "branch": branch.name if branch else None,
                    "service": service.name if service else None,
                }
            bucket = grouped.setdefault(key, {"label": label, "count": 0, "amount": 0})
            bucket["count"] += 1
            snap = appt.price_snapshot or {}
            bucket["amount"] += int(snap.get("amount", 0) or 0)
        row_no += 1
        profile = None
        if c.user_id:
            profile = db.get(Profile, c.user_id)
        result.append(
            {
                "row": row_no,
                "name": c.display_name,
                "national_id": profile.national_id if profile else None,
                "mobile": (
                    db.get(User, c.user_id).phone_e164 if c.user_id else None
                ),
                "degree": degree.title if degree else None,
                "level": admin_data.REFERRAL_STATUS_FA.get(c.status, c.status)
                if c.status in admin_data.REFERRAL_STATUS_FA
                else c.status,
                "services": [
                    {"count": v["count"], "amount": v["amount"], **v["label"]}
                    for v in grouped.values()
                ],
                "total_count": sum(v["count"] for v in grouped.values()),
                "total_amount": sum(v["amount"] for v in grouped.values()),
            }
        )
    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "ردیف", "نام", "کد ملی", "شماره همراه", "مدرک", "سطح",
                "استان", "شهرستان", "مرکز", "سرویس", "تعداد", "مبلغ",
            ]
        )
        for item in result:
            if not item["services"]:
                writer.writerow(
                    [
                        item["row"], item["name"], item["national_id"] or "",
                        item["mobile"] or "", item["degree"] or "", item["level"] or "",
                        "", "", "", "", 0, 0,
                    ]
                )
            for s in item["services"]:
                writer.writerow(
                    [
                        item["row"],
                        item["name"],
                        item["national_id"] or "",
                        item["mobile"] or "",
                        item["degree"] or "",
                        item["level"] or "",
                        s.get("province") or "",
                        s.get("city") or "",
                        s.get("branch") or "",
                        s.get("service") or "",
                        s["count"],
                        s["amount"],
                    ]
                )
        content = "\ufeff" + buf.getvalue()
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=moshavaran.csv"},
        )
    return envelope(data={"rows": result, "group_by": group_by})


@router.get("/reports/invited")
def invited_persons(
    start: int = Query(default=0, ge=0),
    length: int = Query(default=25),
    user: User = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """کاربران معرفی‌شده (doc s.7.3 card 2)."""
    stmt = (
        select(User, Profile)
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(Profile.registration_source.is_not(None))
        .order_by(User.created_at.desc())
    )
    rows = db.execute(stmt).all()
    total = len(rows)
    offset, limit = _paging(start, length, total)
    page = rows[offset : offset + limit] if limit else rows[offset:]
    data = []
    for u, p in page:
        data.append(
            {
                "id": str(u.id),
                "code": p.code if p else None,
                "full_name": f"{p.first_name} {p.last_name}".strip() if p else None,
                "mobile": u.phone_e164,
                "province_fa": _province_name(p.province_code) if p else None,
                "registration_source": p.registration_source if p else None,
                "registered_at": u.created_at.isoformat(),
            }
        )
    return envelope(data={"total": total, "rows": data})


@router.get("/reports/reservation-requests")
def reservation_requests(
    start: int = Query(default=0, ge=0),
    length: int = Query(default=25),
    user: User = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """درخواست‌های رزرو کاربران (doc s.7.3 card 3).

    Doc s.11 item ۱: /referrs-requests and /admin-referrs-requests are the SAME
    page — both routes render this report in the web panel.
    """
    stmt = (
        select(Appointment, Service, Consultant, Branch, User, Profile, Referral)
        .outerjoin(Service, Service.id == Appointment.service_id)
        .outerjoin(Consultant, Consultant.id == Appointment.consultant_id)
        .outerjoin(Branch, Branch.id == Appointment.branch_id)
        .outerjoin(User, User.id == Appointment.user_id)
        .outerjoin(Profile, Profile.user_id == User.id)
        .outerjoin(Referral, Referral.id == Appointment.referral_id)
        .where(Appointment.status.in_(("pending_payment", "confirmed")))
        .order_by(Appointment.created_at.desc())
    )
    rows = db.execute(stmt).all()
    total = len(rows)
    offset, limit = _paging(start, length, total)
    page = rows[offset : offset + limit] if limit else rows[offset:]
    data = []
    for appt, service, consultant, branch, u, p, ref in page:
        data.append(
            {
                "code": appt.code,
                "user": f"{p.first_name} {p.last_name}".strip() if p else None,
                "mobile": u.phone_e164 if u else None,
                "service": service.name if service else None,
                "consultant": consultant.display_name if consultant else None,
                "branch": branch.name if branch else None,
                "referral_code": ref.code if ref else None,
                "status_fa": admin_data.APPOINTMENT_STATUS_FA.get(appt.status, appt.status),
                "start_at": appt.start_at.isoformat(),
            }
        )
    return envelope(data={"total": total, "rows": data})


# ─────────────────── activity log (doc s.3.1.2 item ۲۷) ───────────────────


@router.get("/logs")
def activity_logs(
    q: str | None = None,
    start: int = Query(default=0, ge=0),
    length: int = Query(default=25),
    user: User = Depends(require_permission("logs.read")),
    db: Session = Depends(get_db),
):
    """گزارش فعالیت کاربران — from the immutable audit trail."""
    stmt = (
        select(AuditLog, User, Profile)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .outerjoin(Profile, Profile.user_id == User.id)
        .order_by(AuditLog.created_at.desc())
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.action.ilike(needle),
                AuditLog.outcome.ilike(needle),
                User.phone_e164.ilike(needle),
                Profile.first_name.ilike(needle),
                Profile.last_name.ilike(needle),
            )
        )
    rows = db.execute(stmt).all()
    total = len(rows)
    offset, limit = _paging(start, length, total)
    page = rows[offset : offset + limit] if limit else rows[offset:]
    data = []
    for log, u, p in page:
        data.append(
            {
                "id": str(log.id),
                "action": log.action,
                "outcome": log.outcome,
                "actor": f"{p.first_name} {p.last_name}".strip() if p and p.first_name else None,
                "actor_phone": u.phone_e164 if u else None,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "request_id": log.request_id,
                "ip": log.ip,
                "created_at": log.created_at.isoformat(),
            }
        )
    return envelope(data={"total": total, "rows": data})
