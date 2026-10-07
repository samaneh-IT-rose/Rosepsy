from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.core.phone import normalize_iran_mobile
from app.main import app
from app.services.authz import grant_role
from app.services.seed import seed_roles
from app.services.sms import get_sms_sender

client = TestClient(app)


def login(phone: str) -> tuple[str, str]:
    r = client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["challenge_id"]
    target = normalize_iran_mobile(phone)
    code = [s for s in get_sms_sender().sent if s["phone"] == target][-1]["code"]
    v = client.post("/api/v1/auth/otp/verify", json={"challenge_id": cid, "code": code})
    assert v.status_code == 200, v.text
    data = v.json()["data"]
    return data["access_token"], data["user"]["id"]


def grant(phone: str, role: str) -> tuple[str, str]:
    token, uid = login(phone)
    with SessionLocal() as db:
        seed_roles(db)
        grant_role(db, user_id=UUID(uid), role_name=role)
    return token, uid


def grant_scoped(phone: str, role: str, branch_id: UUID) -> tuple[str, str]:
    token, uid = login(phone)
    with SessionLocal() as db:
        seed_roles(db)
        grant_role(db, user_id=UUID(uid), role_name=role, branch_id=branch_id)
    return token, uid


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def denied_count(user_id: str, action: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM audit.audit_logs "
                "WHERE outcome = 'denied' AND actor_user_id = :u AND action = :a"
            ),
            {"u": UUID(user_id), "a": action},
        ).scalar_one()
