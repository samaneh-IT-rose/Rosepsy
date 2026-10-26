"""Seed roles/permissions, consent versions, and bootstrap the first admin."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone import normalize_iran_mobile
from app.models.consents import ConsentVersion
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
    (
        "national_admin",
        "ادمین ملی",
        "مدیر عامل مجموعه راه زندگی رز سفید ـ دسترسی سراسری به پنل مدیریت",
    ),
]

PERMISSIONS: list[tuple[str, str]] = [
    ("applicants.create", "ثبت متقاضی جدید"),
    ("applicants.read", "مشاهده و جست‌وجوی متقاضیان"),
    ("roles.read", "مشاهده نقش‌ها و مجوزها"),
    ("roles.assign", "تخصیص و سلب نقش کاربران"),
    ("services.manage", "مدیریت تخصص‌ها و خدمات"),
    ("consultants.read", "مشاهده مشاوران"),
    ("consultants.manage", "ایجاد و ویرایش مشاوران و مدارک"),
    ("consultants.review", "بررسی و تأیید صلاحیت مشاوران"),
    ("clinics.manage", "مدیریت مراکز، شعب و خدمات شعبه"),
    ("branches.manage", "ویرایش و انتشار شعبه (با برانچ‌اسکوپ)"),
    ("tariffs.manage", "مدیریت تعرفه‌ها و نسخه‌های قیمت"),
    ("topics.manage", "مدیریت دسته‌بندی موضوعی"),
    ("availability.manage", "مدیریت تقویم و دسترس‌پذیری"),
    ("orders.read", "مشاهده سفارش‌ها"),
    ("invoices.read", "مشاهده فاکتورها"),
    ("consents.manage", "مدیریت نسخه‌های رضایت‌نامه"),
    ("audit.access.read", "مشاهده گزارش دسترسی"),
    ("records.read", "مشاهده پرونده مراجعان مجاز"),
    ("records.manage", "ایجاد پرونده دیجیتال"),
    ("questionnaires.manage", "مدیریت پرسشنامه‌های پرونده"),
    ("encounters.manage", "زمان‌بندی و پایش جلسات"),
    ("notes.manage", "ثبت و تأیید یادداشت جلسه"),
    ("wallet.manage", "مدیریت کیف پول کاربران (شارژ و مشاهده)"),
    ("discounts.manage", "مدیریت کدهای تخفیف"),
    ("refunds.manage", "بررسی، تأیید و اجرای استرداد وجه"),
    ("contents.manage", "مدیریت محتوای عمومی (مقاله/خبر/رسانه)"),
    ("courses.manage", "مدیریت دوره‌ها و آزمون‌های آموزشی"),
    ("organizations.manage", "مدیریت سازمان‌ها، قرارداد و اعضا"),
    ("accounting.manage", "مدیریت کدینگ، اسناد حسابداری و تسویه"),
    ("tickets.manage", "پیگیری تیکت‌های پشتیبانی"),
    ("psych.manage", "مدیریت تست‌های روان‌شناسی و نسخه‌های آن"),
    ("psych.review", "بازبینی علمی نسخه‌ها و نتایج تست (ناظر علمی)"),
    # ── B42 admin panel (doc ساختاریافته) ──
    ("admin.panel", "دسترسی به پنل مدیریت"),
    ("users.manage", "مشاهده و ویرایش کاربران سامانه"),
    ("users.switch_session", "ورود به حساب کاربران (تعویض نشست)"),
    ("reports.read", "مشاهده گزارشات"),
    ("logs.read", "مشاهده گزارش فعالیت کاربران"),
]

GRANTS: dict[str, list[str]] = {
    "reception": [
        "applicants.create",
        "applicants.read",
        "records.manage",
        "encounters.manage",
        "tickets.manage",
    ],
    "consultant": [
        "availability.manage",
        "records.read",
        "notes.manage",
    ],
    "content_manager": [
        "contents.manage",
        "courses.manage",
        "topics.manage",
    ],
    "finance": [
        "orders.read",
        "invoices.read",
        "wallet.manage",
        "discounts.manage",
        "refunds.manage",
        "organizations.manage",
        "accounting.manage",
    ],
    "scientific_reviewer": ["psych.review", "psych.manage"],
    "auditor_dpo": ["audit.access.read"],
    "system_admin": [
        "applicants.create",
        "applicants.read",
        "roles.read",
        "roles.assign",
        "services.manage",
        "consultants.read",
        "consultants.manage",
        "consultants.review",
        "clinics.manage",
        "branches.manage",
        "tariffs.manage",
        "topics.manage",
        "contents.manage",
        "courses.manage",
        "availability.manage",
        "orders.read",
        "invoices.read",
        "wallet.manage",
        "discounts.manage",
        "refunds.manage",
        "organizations.manage",
        "accounting.manage",
        "tickets.manage",
        "consents.manage",
        "audit.access.read",
        "records.read",
        "records.manage",
        "questionnaires.manage",
        "encounters.manage",
        "notes.manage",
        "psych.manage",
        "admin.panel",
        "users.manage",
        "users.switch_session",
        "reports.read",
        "logs.read",
    ],
    "national_admin": [
        "admin.panel",
        "users.manage",
        "users.switch_session",
        "reports.read",
        "logs.read",
        "applicants.read",
        "roles.read",
        "consultants.read",
        "clinics.manage",
        "branches.manage",
        "tariffs.manage",
        "audit.access.read",
        "records.read",
        "encounters.manage",
    ],
}

# DEV PLACEHOLDER texts - final wording requires legal/stakeholder approval.
CONSENT_SEED: list[tuple[str, str, str]] = [
    (
        "treatment",
        "رضایت انجام خدمات مشاوره و درمان",
        "بدین‌وسیله رضایت خود را برای دریافت خدمات مشاوره و درمان در کلینیک رز اعلام "
        "می‌کنم و می‌دانم اطلاعات درمانی من صرفاً با رعایت محرمانگی و مطابق مقررات "
        "استفاده می‌شود. (متن نهایی پس از تأیید حقوقی)",
    ),
    (
        "psych_test",
        "رضایت اجرای آزمون روان‌شناسی",
        "رضایت دارم آزمون روان‌شناسی بر من اجرا شود و نتیجه آن توسط ناظر علمی تفسیر و "
        "در پرونده من نگهداری شود. (متن نهایی پس از تأیید حقوقی)",
    ),
    (
        "marketing",
        "رضایت دریافت پیام‌های اطلاع‌رسانی و تبلیغاتی",
        "رضایت دارم اخبار، دوره‌ها و اطلاع‌رسانی‌های تبلیغاتی کلینیک رز را از طریق "
        "پیامک یا ایمیل دریافت کنم؛ این رضایت مستقل از خدمات درمانی است و هر زمان "
        "قابل ابطال است. (متن نهایی پس از تأیید حقوقی)",
    ),
    (
        "data_sharing",
        "رضایت اشتراک داده",
        "رضایت دارم داده‌های مشخص‌شده من مطابق قرارداد با سازمان مربوط به اشتراک "
        "گذاشته شود؛ یادداشت‌های درمانی مشمول این رضایت نیستند. (متن نهایی پس از "
        "تأیید حقوقی)",
    ),
]


def seed_consent_versions(db: Session) -> int:
    """Create version 1 for each kind if absent. Idempotent."""
    created = 0
    for kind, title_fa, text_fa in CONSENT_SEED:
        exists = db.execute(
            select(ConsentVersion).where(ConsentVersion.kind == kind)
        ).scalar_one_or_none()
        if exists is None:
            db.add(ConsentVersion(kind=kind, version=1, title_fa=title_fa, text_fa=text_fa))
            created += 1
    if created:
        db.commit()
    return created


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
                db.add(RolePermission(role_id=roles[role_name].id, permission_id=perms[code].id))
    db.commit()
    seed_consent_versions(db)


def promote_admin(db: Session, phone_raw: str) -> uuid.UUID:
    """Grant system_admin to an existing user identified by phone."""
    phone = normalize_iran_mobile(phone_raw)
    user = db.execute(select(User).where(User.phone_e164 == phone)).scalar_one_or_none()
    if user is None:
        raise LookupError("کاربر با این شماره یافت نشد؛ ابتدا یک بار با OTP وارد شوید")
    seed_roles(db)
    grant_role(db, user_id=user.id, role_name="system_admin")
    return user.id
