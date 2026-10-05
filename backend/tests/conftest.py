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
CORE_TABLES = ["core.auth_sessions", "core.otp_challenges", "core.profiles", "core.users"]


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
        for table in reversed(CORE_TABLES):
            conn.execute(text("TRUNCATE TABLE " + table + " CASCADE"))
    redis = get_redis()
    for key in redis.scan_iter("rl:otp:*"):
        redis.delete(key)
    get_sms_sender().sent.clear()


@pytest.fixture(autouse=True)
def clean_state(prepare_db):
    _cleanup()
    yield
    _cleanup()
