from uuid import UUID

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h, login

PHONE = iter(range(9141230000, 9141239999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _setup_admin_and_client():
    """admin creates a client user (via OTP login) with active treatment consent."""
    admin_token, _ = grant(_phone(), "system_admin")
    ahok = h(admin_token)
    client_token, client_id = login(_phone())  # the patient
    chok = h(client_token)
    # patient grants treatment consent (self)
    cons = client.post(
        "/api/v1/consents", json={"kind": "treatment"}, headers=chok
    )
    assert cons.status_code == 201, cons.text
    return ahok, admin_token, chok, client_token, client_id


def _mk_record(ahok, client_id: str):
    r = client.post(
        "/api/v1/clinical-records",
        json={"user_id": client_id, "summary": "شروع پرونده"},
        headers=ahok,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _mk_consultant_with_relationship(ahok, client_id: str, record_id: str):
    """Create consultant user+profile, then an encounter linking them."""
    cons_token, cons_user_id = login(_phone())
    cc = client.post(
        "/api/v1/consultants",
        json={"display_name": "دکتر پرونده", "user_id": cons_user_id},
        headers=ahok,
    )
    assert cc.status_code == 201, cc.text
    cid = cc.json()["data"]["id"]
    enc = client.post(
        "/api/v1/encounters",
        json={
            "record_id": record_id,
            "consultant_id": cid,
            "start_at": "2025-06-20T09:00:00Z",
            "end_at": "2025-06-20T09:45:00Z",
        },
        headers=ahok,
    )
    assert enc.status_code == 201, enc.text
    return cons_token, cid, enc.json()["data"]["id"]


def test_record_requires_active_treatment_consent():
    ahok, _admin_token, _chok, _client_token, _client_id = _setup_admin_and_client()
    # a fresh user with NO treatment consent
    _, other_id = login(_phone())
    r = client.post(
        "/api/v1/clinical-records", json={"user_id": other_id}, headers=ahok
    )
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "CONSENT_REQUIRED"

def test_record_create_and_owner_read_audited():
    ahok, _, chok, _, client_id = _setup_admin_and_client()
    record = _mk_record(ahok, client_id)
    assert record["risk_level"] == "unknown"
    dup = client.post(
        "/api/v1/clinical-records", json={"user_id": client_id}, headers=ahok
    )
    assert dup.status_code == 409
    # owner reads own record -> allowed + access event
    mine = client.get("/api/v1/clinical-records/me", headers=chok)
    assert mine.status_code == 200
    assert mine.json()["data"]["id"] == record["id"]
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM audit.access_events "
                "WHERE action = 'clinical.record.read' AND allowed = true "
                "AND resource_id = :rid"
            ),
            {"rid": UUID(record["id"])},
        ).scalar_one()
    assert n >= 1


def test_consultant_without_relationship_denied_and_audited():
    ahok, _, _, _, client_id = _setup_admin_and_client()
    record = _mk_record(ahok, client_id)
    cons_token, _, _ = _mk_consultant_with_relationship(ahok, client_id, record["id"])
    # create a SECOND record for another client: same consultant, no encounter
    other_token, other_client = login(_phone())
    client.post(
        "/api/v1/consents", json={"kind": "treatment"}, headers=h(other_token)
    )
    other_record = _mk_record(ahok, other_client)
    resp = client.get(
        f"/api/v1/clinical-records/{other_record['id']}", headers=h(cons_token)
    )
    assert resp.status_code == 403
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM audit.access_events "
                "WHERE action = 'clinical.record.read' AND allowed = false "
                "AND resource_id = :rid"
            ),
            {"rid": UUID(other_record["id"])},
        ).scalar_one()
    assert n >= 1  # denial recorded per spec


def test_consultant_with_relationship_can_read():
    ahok, _, _, _, client_id = _setup_admin_and_client()
    record = _mk_record(ahok, client_id)
    cons_token, _, _ = _mk_consultant_with_relationship(ahok, client_id, record["id"])
    resp = client.get(f"/api/v1/clinical-records/{record['id']}", headers=h(cons_token))
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == record["id"]


def test_stranger_cannot_read_record():
    ahok, _, _, _, client_id = _setup_admin_and_client()
    record = _mk_record(ahok, client_id)
    stranger_token, _ = login(_phone())
    resp = client.get(
        f"/api/v1/clinical-records/{record['id']}", headers=h(stranger_token)
    )
    assert resp.status_code == 403


def test_owner_attaches_clean_file_to_own_record():
    import httpx

    ahok, _, chok, _, client_id = _setup_admin_and_client()
    record = _mk_record(ahok, client_id)
    intent = client.post(
        "/api/v1/files/upload-intents",
        json={
            "filename": "lab.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(b"%PDF-1.4 lab"),
        },
        headers=chok,
    ).json()["data"]
    httpx.put(intent["upload_url"], content=b"%PDF-1.4 lab", timeout=10)
    client.post(f"/api/v1/files/{intent['id']}/complete", headers=chok)
    attach = client.post(
        f"/api/v1/clinical-records/{record['id']}/files",
        json={"file_id": intent["id"]},
        headers=chok,
    )
    assert attach.status_code == 201, attach.text


def test_submission_locked_to_version():
    ahok, _, chok, _, client_id = _setup_admin_and_client()
    record = _mk_record(ahok, client_id)
    q = client.post(
        "/api/v1/questionnaires",
        json={"title_fa": "پرسشنامه اولیه", "slug": "intake-v1"},
        headers=ahok,
    ).json()["data"]
    v1 = client.post(
        f"/api/v1/questionnaires/{q['id']}/versions",
        json={"schema_json": {"questions": [{"id": "sleep", "type": "int"}]}},
        headers=ahok,
    ).json()["data"]
    sub = client.post(
        "/api/v1/submissions",
        json={"version_id": v1["id"], "answers": {"sleep": 6}},
        headers=chok,
    )
    assert sub.status_code == 201, sub.text
    # owner lists submissions
    listed = client.get(
        f"/api/v1/clinical-records/{record['id']}/submissions", headers=chok
    )
    assert listed.status_code == 200
    assert listed.json()["data"][0]["answers"] == {"sleep": 6}
    # admin (non-owner, non-consultant) denied
    denied = client.get(
        f"/api/v1/clinical-records/{record['id']}/submissions", headers=ahok
    )
    assert denied.status_code == 403


def test_questionnaire_manage_requires_permission():
    token, _ = login(_phone())
    r = client.post(
        "/api/v1/questionnaires", json={"title_fa": "بدون مجوز", "slug": "no-perm"},
        headers=h(token),
    )
    assert r.status_code == 403
