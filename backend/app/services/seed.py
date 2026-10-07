"""Seed roles/permissions and bootstrap the first system admin.

The eight roles mirror the spec role table (s.04/15). Only the permissions
needed so far (B03/B04) are attached; later sprints extend GRANTS.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone import normalize_iran_mobile
from app.models.core import User
from app.models.rbac import Permission, Role, RolePermission
from app.services.authz import grant_role

ROLES: list[tuple[str, str, str]] = [
    ("reception", "پذیرش شعبه", "ثبت مراجع، زمان‌بندی و پیگیری نوبت‌های شعبه"),
    ("branch_manager", "مدیر شعبه", "خدمات و گزارش عملیاتی شعبه"),
    ("consultant", "مشاور", "تقویم، جلسات و پرونده مراجعان مجاز"),
    ("content_manager", "مدیر محتوا/آموزش", "مقاله، خبر، رسانه، دوره و آزمون آموزشی"),
    ("finance", "مالی", "سفارش، فاکتور، استرداد و تسویه"),
    ("system_admin", "مدیر سامانه", "تعریف نقش، تنظیمات، پایش و ممیزی"),
    ("scientific_reviewer", "ناظر علمی", "تأیید محتوای حساس، کلید تست و متن تفسیر"),
    ("auditor_dpo", "حسابرس / DPO", "مشاهده لاگ و گزارش انطباق"),
]

PERMISSIONS: list[tuple[str, str]] = [
    ("applicants.create", "ثبت متقاضی جدید"),
    ("applicants.read", "مشاهده و جست‌وجوی متقاضیان"),
    ("roles.read", "مشاهده نقش‌ها و مجوزها"),
    ("roles.assign", "تخصیص و سلب نقش کاربران"),
]

GRANTS: dict[str, list[str]] = {
    "reception": ["applicants.create", "applicants.read"],
    "system_admin": ["applicants.create", "applicants.read", "roles.read", "roles.assign"],
}


def seed_roles(db: Session) -> None:
    roles: dict[str, Role] = {}
    for name, title_fa, desc in ROLES:
        role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if role is None:
            role = Role(name=name, title_fa=title_fa, description=desc)
            db.add(role)
            db.flush()
        roles[name] = role

    perms: dict[str, Permission] = {}
    for code, title_fa in PERMISSIONS:
        perm = db.execute(
            select(Permission).where(Permission.code == code)
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(code=code, title_fa=title_fa)
            db.add(perm)
            db.flush()
        perms[code] = perm

    for role_name, codes in GRANTS.items():
        for code in codes:
            link = db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == roles[role_name].id,
                    RolePermission.permission_id == perms[code].id,
                )
            ).scalar_one_or_none()
            if link is None:
                db.add(
                    RolePermission(role_id=roles[role_name].id, permission_id=perms[code].id)
                )
    db.commit()


def promote_admin(db: Session, phone_raw: str) -> uuid.UUID:
    """Grant system_admin to an existing user identified by phone."""
    phone = normalize_iran_mobile(phone_raw)
    user = db.execute(select(User).where(User.phone_e164 == phone)).scalar_one_or_none()
    if user is None:
        raise LookupError("کاربر با این شماره یافت نشد؛ ابتدا یک بار با OTP وارد شوید")
    seed_roles(db)
    grant_role(db, user_id=user.id, role_name="system_admin")
    return user.id
