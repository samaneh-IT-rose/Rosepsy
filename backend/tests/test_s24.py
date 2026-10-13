from uuid import UUID

from tests.helpers import client, grant, h, login

PHONE = iter(range(9141270000, 9141279999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _base():
    """admin + patient(with consent+record) + consultant linked by encounter."""
    admin_token, _ = grant(_phone(), "system_admin")
    ahok = h(admin_token)
    patient_token, patient_id = login(_phone())
    phok = h(patient_token)
    client.post("/api/v1/consents", json={"kind": "treatment"}, headers=phok)
    record = client.post(
        "/api/v1/clinical-records", json={"user_id": patient_id}, headers=ahok
    ).json()["data"]
    cons_token, cons_user_id = login(_phone())
    cid = client.post(
        "/api/v1/consultants",
        json={"display_name": "دکتر لیست", "user_id": cons_user_id},
        headers=ahok,
    ).json()["data"]["id"]
    enc = client.post(
        "/api/v1/encounters",
        json={
            "record_id": record["id"],
            "consultant_id": cid,
            "start_at": "2025-07-01T10:00:00Z",
            "end_at": "2025-07-01T10:45:00Z",
        },
        headers=ahok,
    ).json()["data"]
    return ahok, phok, h(cons_token), record, enc["id"]


def test_my_encounters_lists_only_own():
    ahok, phok, chok, record, enc_id = _base()
    # consultant sees own encounter
    mine = client.get("/api/v1/encounters/mine", headers=chok)
    assert mine.status_code == 200
    ids = [e["id"] for e in mine.json()["data"]]
    assert enc_id in ids
    # another consultant sees none
    other_token, _ = login(_phone())
    other = client.get("/api/v1/encounters/mine", headers=h(other_token))
    assert other.json()["data"] == []
    # non-consultant rejected
    resp = client.get("/api/v1/encounters/mine", headers=phok)
    assert resp.status_code == 403
    assert resp.json()["errors"][0]["code"] == "NOT_A_CONSULTANT"


def test_encounter_record_via_session_link():
    ahok, phok, chok, record, enc_id = _base()
    resp = client.get(f"/api/v1/encounters/{enc_id}/record", headers=chok)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == record["id"]


def test_encounter_record_access_event_logged():
    ahok, phok, chok, record, enc_id = _base()
    client.get(f"/api/v1/encounters/{enc_id}/record", headers=chok)
    from sqlalchemy import text

    from app.core.db import engine

    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM audit.access_events "
                "WHERE action = 'clinical.record.read' AND resource_id = :rid "
                "AND detail->>'via' = 'encounter'"
            ),
            {"rid": UUID(record["id"])},
        ).scalar_one()
    assert n >= 1
