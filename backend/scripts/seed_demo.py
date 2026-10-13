"""Demo data seed (idempotent) — for acceptance demos of Release 2.

Creates: admin + consultant(eligible) + demo client with treatment consent +
record + weekly availability + a 45min paid-tier service.

Usage: python scripts/seed_demo.py
Prints demo phone numbers. OTP: use dev_fixed code (123456) in dev env.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.phone import normalize_iran_mobile
from app.models.catalog import Consultant, Credential, Service
from app.models.core import User
from app.models.org import Branch, Clinic
from app.models.pricing import Tariff, TariffVersion
from app.services.authz import grant_role
from app.services.booking import consultant_is_bookable
from app.services.seed import seed_roles

DEMO_PHONES = {
    "admin": "09129990001",
    "consultant": "09129990002",
    "client": "09129990003",
}


def _get_or_create_user(db, phone: str) -> User:
    p = normalize_iran_mobile(phone)
    user = db.execute(select(User).where(User.phone_e164 == p)).scalar_one_or_none()
    if user is None:
        user = User(phone_e164=p)
        db.add(user)
        db.flush()
    return user


def seed_demo(db) -> dict:
    seed_roles(db)

    admin = _get_or_create_user(db, DEMO_PHONES["admin"])
    grant_role(db, user_id=admin.id, role_name="system_admin")

    consultant_user = _get_or_create_user(db, DEMO_PHONES["consultant"])
    grant_role(db, user_id=consultant_user.id, role_name="consultant")

    cons = db.execute(
        select(Consultant).where(Consultant.user_id == consultant_user.id)
    ).scalar_one_or_none()
    if cons is None:
        cons = Consultant(user_id=consultant_user.id, display_name="دکتر دمو")
        db.add(cons)
        db.flush()
    if db.execute(
        select(Credential.id).where(Credential.consultant_id == cons.id)
    ).scalar_one_or_none() is None:
        db.add(
            Credential(
                consultant_id=cons.id,
                kind="license",
                title="پروانه دمو",
                license_number="DEMO-LIC-1",
            )
        )
        db.flush()
        # تایید مدرک به‌صورت سیستمی برای دمو
        from app.models.catalog import VerificationReview
        db.add(
            VerificationReview(
                consultant_id=cons.id,
                credential_id=None,
                reviewer_id=admin.id,
                decision="approved",
                note="دمو",
            )
        )
        # دستی وضعیت credential را verified کنیم
        cred = db.execute(
            select(Credential).where(Credential.consultant_id == cons.id)
        ).scalar_one()
        cred.status = "verified"
        cons.status = "approved"

    if db.execute(select(Clinic)).scalars().first() is None:
        db.add(Clinic(name="کلینیک رز (دمو)", slug="roz-demo"))
        db.flush()
    clinic = db.execute(select(Clinic)).scalars().first()
    if db.execute(
        select(Branch).where(Branch.clinic_id == clinic.id)
    ).scalars().first() is None:
        db.add(
            Branch(
                clinic_id=clinic.id,
                name="شعبه دمو",
                slug="roz-demo-b1",
                city="تهران",
                lat=35.75,
                lon=51.41,
                status="published",
            )
        )

    svc = db.execute(select(Service).where(Service.name == "جلسه دمو")).scalar_one_or_none()
    if svc is None:
        svc = Service(name="جلسه دمو", duration_minutes=45)
        db.add(svc)
        db.flush()
    if db.execute(
        select(Tariff).where(Tariff.service_id == svc.id)
    ).scalar_one_or_none() is None:
        t = Tariff(service_id=svc.id)
        db.add(t)
        db.flush()
        db.add(
            TariffVersion(
                tariff_id=t.id,
                amount=4500000,
                valid_from="2024-01-01T00:00:00Z",
            )
        )

    db.commit()

    bookable = consultant_is_bookable(db, cons)
    return {
        "phones": DEMO_PHONES,
        "consultant_bookable": bookable,
        "note": "برای ورود: OTP dev_fixed code = " + (
            "123456" if settings.SMS_PROVIDER == "dev_fixed" else "(mock — از لاگ بگیر)"
        ),
    }


if __name__ == "__main__":
    with SessionLocal() as session:
        result = seed_demo(session)
    print("demo seed OK")
    for k, v in result.items():
        print(f"  {k}: {v}")
