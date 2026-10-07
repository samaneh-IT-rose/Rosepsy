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


def _login(phone: str) -> tuple[str, str]:
    r = client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["challenge_id"]
    target = normalize_iran_mobile(phone)
    code = [s for s in get_sms_sender().sent if s["phone"] == target][-1]["code"]
    v = client.post("/api/v1/auth/otp/verify", json={"challenge_id": cid, "code": code})
    assert v.status_code == 200, v.text
    data = v.json()["data"]
    return data["access_token"], data["user"]["id"]


def _grant(phone: str, role: str) -> tuple[str, str]:
    token, uid = _login(phone)
    with SessionLocal() as db:
        seed_roles(db)
        grant_role(db, user_id=UUID(uid), role_name=role)
    return token, uid


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- B03: applicants ----------


def test_unauthenticated_applicants_rejected():
    resp = client.post(
        "/api/v1/applicants", json={"full_name": "Ali Rezaei", "phone": "09121130001"}
    )
    assert resp.status_code == 401


def test_plain_user_cannot_create_applicant_and_denial_is_audited():
    token, uid = _login("09121130002")
    resp = client.post(
        "/api/v1/applicants",
        json={"full_name": "Sara Ahmadi", "phone": "09121130003"},
        headers=_h(token),
    )
    assert resp.status_code == 403
    assert resp.json()["errors"][0]["code"] == "FORBIDDEN"
    with engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM audit.audit_logs "
                "WHERE outcome = 'denied' AND actor_user_id = :u "
                "AND action = 'permission:applicants.create'"
            ),
            {"u": UUID(uid)},
        ).scalar_one()
    assert count == 1  # the denial is RECORDED (spec rule for B04)


def test_reception_can_create_applicant_and_action_is_audited():
    token, uid = _grant("09121130004", "reception")
    resp = client.post(
        "/api/v1/applicants",
        json={"full_name": "Reza Karimi", "phone": "09121130005", "notes": "تماس اول"},
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["phone"] == "+989121130005"
    assert data["created_by"] == uid
    with engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM audit.audit_logs "
                "WHERE outcome = 'allowed' AND action = 'applicant.create'"
            )
        ).scalar_one()
    assert count == 1


def test_duplicate_applicant_phone_rejected():
    token, _ = _grant("09121130006", "reception")
    body = {"full_name": "Mina Rahimi", "phone": "09121130007"}
    first = client.post("/api/v1/applicants", json=body, headers=_h(token))
    assert first.status_code == 201
    second = client.post("/api/v1/applicants", json=body, headers=_h(token))
    assert second.status_code == 409
    err = second.json()["errors"][0]
    assert err["code"] == "DUPLICATE_APPLICANT"
    assert err["existing_applicant_id"] == first.json()["data"]["id"]


def test_applicant_phone_matching_existing_user_rejected():
    token, uid = _grant("09121130008", "reception")
    resp = client.post(
        "/api/v1/applicants",
        json={"full_name": "Hasan Ghasemi", "phone": "09121130008"},
        headers=_h(token),
    )
    assert resp.status_code == 409
    err = resp.json()["errors"][0]
    assert err["code"] == "APPLICANT_EXISTS_AS_USER"
    assert err["existing_user_id"] == uid


def test_search_applicants_by_name_and_phone():
    token, _ = _grant("09121130009", "reception")
    h = _h(token)
    client.post(
        "/api/v1/applicants",
        json={"full_name": "Ladan Moradi", "phone": "09121130010"},
        headers=h,
    )
    client.post(
        "/api/v1/applicants",
        json={"full_name": "Omid Tabatabaei", "phone": "09121130011"},
        headers=h,
    )
    by_name = client.get("/api/v1/applicants?q=Ladan", headers=h)
    assert by_name.status_code == 200
    assert by_name.json()["meta"]["total"] == 1
    assert by_name.json()["data"][0]["full_name"] == "Ladan Moradi"
    by_phone = client.get("/api/v1/applicants?q=30011", headers=h)
    assert by_phone.json()["meta"]["total"] == 1
    assert by_phone.json()["data"][0]["phone"] == "+989121130011"
    all_rows = client.get("/api/v1/applicants", headers=h)
    assert all_rows.json()["meta"]["total"] == 2


def test_get_applicant_by_id_and_missing():
    token, _ = _grant("09121130012", "reception")
    h = _h(token)
    created = client.post(
        "/api/v1/applicants",
        json={"full_name": "Neda Sahraei", "phone": "09121130013"},
        headers=h,
    )
    aid = created.json()["data"]["id"]
    got = client.get(f"/api/v1/applicants/{aid}", headers=h)
    assert got.status_code == 200
    assert got.json()["data"]["full_name"] == "Neda Sahraei"
    missing = client.get(f"/api/v1/applicants/{UUID(int=0)}", headers=h)
    assert missing.status_code == 404


def test_applicant_invalid_phone():
    token, _ = _grant("09121130014", "reception")
    resp = client.post(
        "/api/v1/applicants",
        json={"full_name": "Bad Phone", "phone": "1234567890"},
        headers=_h(token),
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "INVALID_PHONE"


# ---------- B04: roles and access matrix ----------


def test_roles_list_requires_permission():
    token, _ = _login("09121130015")
    resp = client.get("/api/v1/roles", headers=_h(token))
    assert resp.status_code == 403


def test_roles_list_shows_seeded_permissions():
    token, _ = _grant("09121130016", "system_admin")
    resp = client.get("/api/v1/roles", headers=_h(token))
    assert resp.status_code == 200
    roles = {r["name"]: r for r in resp.json()["data"]}
    assert "reception" in roles
    assert "applicants.create" in roles["reception"]["permissions"]
    assert "roles.assign" in roles["system_admin"]["permissions"]


def test_admin_assigns_role_which_grants_permission_matrix():
    admin_token, _ = _grant("09121130017", "system_admin")
    target_token, target_id = _login("09121130018")
    before = client.post(
        "/api/v1/applicants",
        json={"full_name": "Kaveh Nazari", "phone": "09121130019"},
        headers=_h(target_token),
    )
    assert before.status_code == 403  # no role yet
    assigned = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role": "reception"},
        headers=_h(admin_token),
    )
    assert assigned.status_code == 201, assigned.text
    after = client.post(
        "/api/v1/applicants",
        json={"full_name": "Kaveh Nazari", "phone": "09121130019"},
        headers=_h(target_token),
    )
    assert after.status_code == 201  # permission granted via role


def test_duplicate_assignment_conflicts():
    admin_token, _ = _grant("09121130020", "system_admin")
    _, target_id = _login("09121130021")
    first = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role": "reception"},
        headers=_h(admin_token),
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role": "reception"},
        headers=_h(admin_token),
    )
    assert second.status_code == 409
    assert second.json()["errors"][0]["code"] == "ROLE_ALREADY_ASSIGNED"


def test_revoke_role_removes_permission():
    admin_token, _ = _grant("09121130022", "system_admin")
    target_token, target_id = _login("09121130023")
    assigned = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role": "reception"},
        headers=_h(admin_token),
    )
    grant_id = assigned.json()["data"]["grant_id"]
    revoked = client.delete(
        f"/api/v1/users/{target_id}/roles/{grant_id}", headers=_h(admin_token)
    )
    assert revoked.status_code == 200
    denied = client.post(
        "/api/v1/applicants",
        json={"full_name": "Parviz Sadri", "phone": "09121130024"},
        headers=_h(target_token),
    )
    assert denied.status_code == 403


def test_assign_role_to_missing_user_404():
    admin_token, _ = _grant("09121130025", "system_admin")
    resp = client.post(
        f"/api/v1/users/{UUID(int=1)}/roles",
        json={"role": "reception"},
        headers=_h(admin_token),
    )
    assert resp.status_code == 404


def test_assign_unknown_role_404():
    admin_token, _ = _grant("09121130026", "system_admin")
    _, target_id = _login("09121130027")
    resp = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role": "no_such_role"},
        headers=_h(admin_token),
    )
    assert resp.status_code == 404
    assert resp.json()["errors"][0]["code"] == "ROLE_NOT_FOUND"


def test_me_returns_assigned_roles():
    token, _ = _grant("09121130028", "reception")
    me = client.get("/api/v1/me", headers=_h(token))
    assert me.status_code == 200
    assert me.json()["data"]["roles"] == ["reception"]
