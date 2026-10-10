import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://roz:roz_dev@localhost:5432/roz")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OTP_PEPPER", "test-pepper")

import pytest
from sqlalchemy import text

from app.core.db import Base, engine
from app.core.redis_client import get_redis
from app.services.sms import get_sms_sender

SCHEMAS = ["core", "booking", "clinical", "finance", "content", "edu", "audit"]
TABLES = [
    "finance.invoice_items",
    "finance.invoices",
    "finance.payments",
    "finance.orders",
    "booking.appointments",
    "booking.slot_claims",
    "booking.availability_exceptions",
    "booking.availability_weekly_rules",
    "core.auth_sessions",
    "core.user_roles",
    "core.role_permissions",
    "core.otp_challenges",
    "core.applicants",
    "core.profiles",
    "core.users",
    "core.roles",
    "core.permissions",
    "core.verification_reviews",
    "core.credentials",
    "core.consultants",
    "core.services",
    "core.specialties",
    "core.branch_service_offerings",
    "core.branches",
    "core.clinics",
    "core.tariff_versions",
    "core.tariffs",
    "core.topics",
    "core.files",
    "core.messages",
    "core.message_thread_members",
    "core.message_threads",
    "core.communication_preferences",
    "core.notifications",
    "core.notification_events",
    "audit.audit_logs",
]

EXCLUSION_CONSTRAINTS = [
    (
        "ex_booking_slot_claims_active",
        "ALTER TABLE booking.slot_claims ADD CONSTRAINT ex_booking_slot_claims_active "
        "EXCLUDE USING gist (consultant_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) "
        "WHERE (status = 'held')",
    ),
    (
        "ex_booking_appointments_active",
        "ALTER TABLE booking.appointments ADD CONSTRAINT ex_booking_appointments_active "
        "EXCLUDE USING gist (consultant_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) "
        "WHERE (status IN ('pending_payment', 'confirmed', 'in_progress'))",
    ),
]


@pytest.fixture(scope="session", autouse=True)
def prepare_db():
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(text('CREATE SCHEMA IF NOT EXISTS "' + schema + '"'))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS finance.invoice_number_seq START 1"))
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for name, ddl in EXCLUSION_CONSTRAINTS:
            exists = conn.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}
            ).scalar()
            if not exists:
                conn.execute(text(ddl))
    yield


def _cleanup() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT table_schema || '.' || table_name FROM information_schema.tables "
                "WHERE table_schema IN ('core','booking','finance','audit')"
            )
        ).scalars().all()
        existing = set(rows)
        targets = [t for t in TABLES if t in existing]
        if targets:
            conn.execute(text("TRUNCATE TABLE " + ", ".join(targets) + " CASCADE"))
    redis = get_redis()
    for key in redis.scan_iter("rl:otp:*"):
        redis.delete(key)
    get_sms_sender().sent.clear()


@pytest.fixture(autouse=True)
def clean_state(prepare_db):
    _cleanup()
    yield
    _cleanup()
