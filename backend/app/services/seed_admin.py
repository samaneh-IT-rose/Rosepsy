"""Idempotent seeding for the admin panel (B42) — mirrors the structured doc.

- core.provinces / cities      (doc s.9 + s.10 city names)
- clinic groups + 101 centers  (doc s.10 appendix + the «باینگان» center of s.5.4)
- the two sample records of the doc (s.4.6 users table, s.5 پرونده کاربر)
- services / consultant / referral / appointments for the s.5.4 sample table
- a handful of extra demo users and sessions so filters and reports have data

Run:  python -m scripts.seed_admin [--admin-phone 09xxxxxxxxx]
"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone import normalize_iran_mobile
from app.models.admin import City, ClinicGroup, Province, Referral
from app.models.booking import Appointment
from app.models.catalog import Consultant, Credential, Service
from app.models.core import Profile, User
from app.models.org import Branch, Clinic
from app.services import admin_data, centers_seed_data
from app.services.authz import grant_role
from app.services.seed import seed_roles

TEHRAN = ZoneInfo("Asia/Tehran")
PARENT_CLINIC_NAME = "مجموعه راه زندگی رز سفید"


def jalali_to_gregorian(jy: int, jm: int, jd: int):
    """Standard Jalali→Gregorian conversion (Borkowski algorithm, compact)."""
    jy += 1595
    days = (
        -355668
        + (365 * jy)
        + ((jy // 33) * 8)
        + (((jy % 33) + 3) // 4)
        + jd
        + ((jm < 7) * (jm - 1) * 31)
        + ((jm > 6) * ((jm - 7) * 30) + 186)
    )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    months = [0, 31, (29 if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0) else 28),
              31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for i, m in enumerate(months[1:], start=1):
        if gd <= m:
            gm = i
            break
        gd -= m
    return gy, gm, gd


def jdatetime(jy: int, jm: int, jd: int, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return datetime(gy, gm, gd, hh, mm, ss, tzinfo=TEHRAN)


def jdate(jy: int, jm: int, jd: int):
    return jdatetime(jy, jm, jd).date()


PROVINCE_CODE = {name: code for code, name in admin_data.PROVINCES}


def seed_provinces_and_cities(db: Session) -> None:
    for code, name in admin_data.PROVINCES:
        if code == 0:
            continue  # «کل کشور» is filter-only, never stored
        if db.get(Province, code) is None:
            db.add(Province(code=code, name=name))
    db.flush()
    # Dedupe (province, city) pairs first: the doc appendix itself contains a
    # duplicate city («اصلاندوز» twice under اردبیل, doc s.11 #11) and the
    # session has autoflush=False, so per-row existence checks would not see
    # pending inserts and the batch would collide on ux_core_cities_province_name.
    seen: set[tuple[int, str]] = set()
    for _name, province_name, city, _legacy in (
        centers_seed_data.CENTERS + centers_seed_data.EXTRA_CENTERS
    ):
        pcode = PROVINCE_CODE[province_name]
        if (pcode, city) in seen:
            continue
        seen.add((pcode, city))
        exists = db.execute(
            select(City).where(City.province_code == pcode, City.name == city)
        ).scalar_one_or_none()
        if exists is None:
            db.add(City(province_code=pcode, name=city))
    db.commit()


def seed_centers(db: Session) -> int:
    clinic = db.execute(
        select(Clinic).where(Clinic.name == PARENT_CLINIC_NAME)
    ).scalar_one_or_none()
    if clinic is None:
        clinic = Clinic(name=PARENT_CLINIC_NAME, slug="rose-white-lifestyle")
        db.add(clinic)
        db.flush()
    groups: dict[str, ClinicGroup] = {}
    for gname in ("ادارات", "مراکز"):
        g = db.execute(select(ClinicGroup).where(ClinicGroup.name == gname)).scalar_one_or_none()
        if g is None:
            g = ClinicGroup(name=gname)
            db.add(g)
            db.flush()
        groups[gname] = g
    created = 0
    for name, province_name, city, legacy in (
        centers_seed_data.CENTERS + centers_seed_data.EXTRA_CENTERS
    ):
        exists = db.execute(
            select(Branch).where(Branch.legacy_code == legacy)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        group = (
            groups["ادارات"]
            if name.startswith("اداره") or name.startswith("(اداره")
            else groups["مراکز"]
        )
        db.add(
            Branch(
                clinic_id=clinic.id,
                name=name,
                slug=f"center-{legacy}",
                province=province_name,
                city=city,
                lat=0,
                lon=0,
                status="published",  # doc s.10: all appendix records are فعال
                legacy_code=legacy,
                clinic_group_id=group.id,
            )
        )
        created += 1
    # Two clearly-labelled inactive demo centers so the «غیرفعال» filter (s.6.3)
    # returns results as well.
    for demo_name, demo_city, demo_prov in (
        ("مرکز نمونه ـ غیرفعال ۱", "تهران", "تهران"),
        ("مرکز نمونه ـ غیرفعال ۲", "مشهد", "خراسان رضوی"),
    ):
        exists = db.execute(select(Branch).where(Branch.name == demo_name)).scalar_one_or_none()
        if exists is None:
            db.add(
                Branch(
                    clinic_id=clinic.id,
                    name=demo_name,
                    slug=f"demo-{uuid.uuid4().hex[:8]}",
                    province=demo_prov,
                    city=demo_city,
                    lat=0,
                    lon=0,
                    status="draft",
                    clinic_group_id=groups["مراکز"].id,
                )
            )
            created += 1
    db.commit()
    return created


def _ensure_user(db: Session, phone_raw: str, **profile_kwargs) -> tuple[User, Profile]:
    phone = normalize_iran_mobile(phone_raw)
    user = db.execute(select(User).where(User.phone_e164 == phone)).scalar_one_or_none()
    if user is None:
        user = User(phone_e164=phone)
        db.add(user)
        db.flush()
    profile = db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
        db.flush()
    for key, value in profile_kwargs.items():
        if value is not None and getattr(profile, key) is None:
            setattr(profile, key, value)
    db.flush()
    return user, profile


SERVICES_DEF = [
    ("مشاوره فردی ـ حضوری", "in_person", 60),
    ("مشاوره روان‌درمانی", "in_person", 90),
    ("مشاوره گروهی", "group", 120),
]


def seed_services_and_consultant(db: Session) -> dict:
    services: dict[str, Service] = {}
    for name, stype, minutes in SERVICES_DEF:
        s = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
        if s is None:
            s = Service(name=name, session_type=stype, duration_minutes=minutes)
            db.add(s)
            db.flush()
        services[name] = s

    CONSULTANT_PHONE = "09121234567"
    consultant_user, consultant_profile = _ensure_user(
        db,
        CONSULTANT_PHONE,
        first_name="پروانه",
        last_name="سهرابی منفرد",
        national_id="0912345678",
        education="کارشناسی ارشد",
        gender="female",
        province_code=8,
        city="تهران",
    )
    consultant = db.execute(
        select(Consultant).where(Consultant.display_name == "پروانه سهرابی منفرد")
    ).scalar_one_or_none()
    if consultant is None:
        consultant = Consultant(
            user_id=consultant_user.id,
            display_name="پروانه سهرابی منفرد",
            status="approved",
        )
        db.add(consultant)
        db.flush()
        db.add(
            Credential(
                consultant_id=consultant.id,
                kind="degree",
                title="کارشناسی ارشد روان‌شناسی بالینی",
                license_number=f"LIC-{uuid.uuid4().hex[:8].upper()}",
                status="approved",
            )
        )
        db.flush()
    return {"services": services, "consultant": consultant}


def seed_doc_samples(db: Session, consultant: Consultant, services: dict[str, Service]) -> None:
    """The two sample records of the doc: s.4.6 (users table) and s.5 (پرونده)."""
    # ── s.4.6: زلیخا برهانی (سمنان) — last login never happened ──
    user_a, profile_a = _ensure_user(
        db,
        "09195449862",
        first_name="زلیخا",
        last_name="برهانی",
        father_name="شیرآقا",
        username="6429830047",
        national_id="6429830047",
        gender="female",
        education="بی‌سواد",
        province_code=15,
        city="سمنان",
    )
    if profile_a.code is None or profile_a.code == 463000:
        profile_a.code = 463887
    if profile_a.birth_date is None:
        profile_a.birth_date = jdate(1352, 3, 1)
    # doc: تاریخ ثبت‌نام ۱۴۰۵/۰۷/۱۲ — align the created_at with the sample.
    if user_a.created_at.year < 2026:
        user_a.created_at = jdatetime(1405, 7, 12, 9, 0, 0)
    db.flush()

    # ── s.5: پرونده کاربر (کرمانشاه/پاوه) + جدول خدمات s.5.4 ──
    address = (
        "استان کرمانشاه، شهرستان پاوه، بخش باینگان، شهر بان وره، بانوره، "
        "خیابان علماء، کوچه رودخانه، پلاک ۰، طبقه همکف"
    )
    user_b, profile_b = _ensure_user(
        db,
        "09189361058",
        first_name="زهرا",
        last_name="احمدی",  # doc s.5 does not name this user — demo value
        father_name="نورالدین",
        national_id="3220146635",
        education="ابتدایی",
        gender="female",
        marital_status="married",
        province_code=22,
        city="",  # doc: شهر خالی
        address=address,
        registration_source="توسط سها",
        email=None,
    )
    if profile_b.birth_date is None:
        profile_b.birth_date = jdate(1374, 1, 25)  # سن ۳۱ (محاسبه‌شده) — s.5.2

    branch_bayangan = db.execute(
        select(Branch).where(Branch.name == "باینگان")
    ).scalar_one_or_none()

    referral = db.execute(
        select(Referral).where(Referral.code == 100136613430)
    ).scalar_one_or_none()
    if referral is None:
        referral = Referral(
            user_id=user_b.id,
            contract_title="مددجو",
            user_tariff=0,
            status="under_review",  # «در حال بررسی» (s.5.4)
            consultant_id=consultant.id,
            branch_id=branch_bayangan.id if branch_bayangan else None,
            source="سها",
            created_by=user_b.id,
        )
        db.add(referral)
        db.flush()

    samples = [  # (code, service, acute, jy/jm/jd start, h,m,s, end h,m,s)
        (279086, "مشاوره فردی ـ حضوری", "no", (1404, 11, 30), (2, 41, 17), (6, 20, 43)),
        (281947, "مشاوره فردی ـ حضوری", "no", (1404, 12, 3), (10, 11, 43), (13, 46, 51)),
        (518235, "مشاوره روان‌درمانی", "pending", (1405, 7, 12), (7, 4, 28), (11, 9, 39)),
    ]
    for code, service_name, acute, jday, t_start, t_end in samples:
        exists = db.execute(
            select(Appointment).where(Appointment.code == code)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        start = jdatetime(*jday, *t_start)
        end = jdatetime(*jday, *t_end)
        db.add(
            Appointment(
                code=code,
                user_id=user_b.id,
                consultant_id=consultant.id,
                service_id=services[service_name].id,
                branch_id=branch_bayangan.id if branch_bayangan else None,
                referral_id=referral.id,
                start_at=start,
                end_at=end,
                status="pending_payment",
                acute_status=acute,
            )
        )
    db.commit()


EXTRA_USERS = [
    # (phone, first, last, father, gender, education, province_code, city, source)
    ("09131110001", "مریم", "کاظمی", "حسن", "female", "دیپلم", 4, "اصفهان", "معرفی"),
    ("09131110002", "علی", "رضایی", "محمد", "male", "کارشناسی", 8, "تهران", None),
    ("09131110003", "فاطمه", "نیکو", "رضا", "female", "کارشناسی ارشد", 17, "شیراز", "معرفی"),
    ("09131110004", "حسین", "مرادی", "قربان", "male", "متوسطه", 13, "اهواز", None),
    ("09131110005", "سارا", "جعفری", "اکبر", "female", "دکتری", 8, "تهران", "توسط سها"),
    ("09131110006", "مهدی", "قاسمی", "علی", "male", "دیپلم", 11, "مشهد", None),
    ("09131110007", "نرگس", "سلطانی", "محمود", "female", "فوق دیپلم", 26, "رشت", "معرفی"),
    ("09131110008", "امیر", "زمانی", "کریم", "male", "ابتدایی", 16, "زاهدان", None),
    ("09131110009", "لیلا", "حیدری", "ناصر", "female", "کارشناسی", 1, "تبریز", None),
    ("09131110010", "رضا", "بهمنی", "جواد", "male", "راهنمایی", 30, "همدان", "توسط سها"),
    ("09131110011", "پریسا", "شریفی", "یدالله", "female", "دیپلم", 27, "ساری", None),
    ("09131110012", "کامران", "یوسفی", "داریوش", "male", "کارشناسی", 24, "گرگان", None),
]


def seed_extra_users(db: Session) -> None:
    for phone, first, last, father, gender, edu, pcode, city, source in EXTRA_USERS:
        _ensure_user(
            db,
            phone,
            first_name=first,
            last_name=last,
            father_name=father,
            gender=gender,
            education=edu,
            province_code=pcode,
            city=city,
            registration_source=source,
            national_id=None,
        )
    db.commit()


def seed_extra_sessions(db: Session, consultant: Consultant, services: dict[str, Service]) -> None:
    """A few more sessions so the event/consultant reports show variety."""
    users = db.execute(select(User).order_by(User.created_at)).scalars().all()[1:6]
    branch = db.execute(select(Branch).where(Branch.status == "published")).scalars().first()
    specs = [
        ("completed", "no", (1404, 10, 15), (9, 0, 0), (10, 30, 0), "مشاوره فردی ـ حضوری"),
        ("completed", "yes", (1404, 10, 20), (11, 0, 0), (12, 30, 0), "مشاوره روان‌درمانی"),
        ("confirmed", "no", (1405, 8, 10), (8, 0, 0), (9, 30, 0), "مشاوره فردی ـ حضوری"),
        ("in_progress", "pending", (1405, 8, 12), (16, 0, 0), (17, 30, 0), "مشاوره گروهی"),
        ("completed", "no", (1404, 9, 5), (14, 0, 0), (16, 0, 0), "مشاوره گروهی"),
    ]
    for i, (status, acute, jday, t_start, t_end, service_name) in enumerate(specs):
        code = 280_100 + i
        exists = db.execute(
            select(Appointment).where(Appointment.code == code)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        target = users[i % len(users)]
        referral = Referral(
            user_id=target.id,
            contract_title="مددجو" if i % 2 == 0 else "سازمانی",
            user_tariff=0 if i % 2 == 0 else 350000,
            status="approved" if status == "completed" else "under_review",
            consultant_id=consultant.id,
            branch_id=branch.id if branch else None,
            source="سها",
        )
        db.add(referral)
        db.flush()
        db.add(
            Appointment(
                code=code,
                user_id=target.id,
                consultant_id=consultant.id,
                service_id=services[service_name].id,
                branch_id=branch.id if branch else None,
                referral_id=referral.id,
                start_at=jdatetime(*jday, *t_start),
                end_at=jdatetime(*jday, *t_end),
                status=status,
                acute_status=acute,
                price_snapshot=(
                    {"amount": 350000, "currency": "IRR"} if i % 2 == 1 else None
                ),
            )
        )
    db.commit()


def run_full_seed(db: Session) -> dict:
    seed_roles(db)
    seed_provinces_and_cities(db)
    centers_created = seed_centers(db)
    bundle = seed_services_and_consultant(db)
    seed_doc_samples(db, bundle["consultant"], bundle["services"])
    seed_extra_users(db)
    seed_extra_sessions(db, bundle["consultant"], bundle["services"])
    return {"centers_created": centers_created}


def promote_national_admin(db: Session, phone_raw: str) -> str:
    phone = normalize_iran_mobile(phone_raw)
    user = db.execute(select(User).where(User.phone_e164 == phone)).scalar_one_or_none()
    if user is None:
        # Bootstrap convenience: create the account so a fresh deployment can
        # promote its first national admin without an OTP round-trip.
        user = User(phone_e164=phone)
        db.add(user)
        db.flush()
    seed_roles(db)
    grant_role(db, user_id=user.id, role_name="national_admin")
    return str(user.id)
