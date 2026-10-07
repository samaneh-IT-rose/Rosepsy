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
    "audit.audit_logs",
]


@pytest.fixture(scope="session", autouse=True)
def prepare_db():
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(text('CREATE SCHEMA IF NOT EXISTS "' + schema + '"'))
    import app.models  # noqa: F401  (register tables on metadata)

    Base.metadata.create_all(engine)
    yield


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE " + ", ".join(TABLES) + " CASCADE"))
    redis = get_redis()
    for key in redis.scan_iter("rl:otp:*"):
        redis.delete(key)
    get_sms_sender().sent.clear()


@pytest.fixture(autouse=True)
def clean_state(prepare_db):
    _cleanup()
    yield
    _cleanup()
