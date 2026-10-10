from uuid import UUID

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h, login

PHONE = iter(range(9141240000, 9141249999))


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
        json={"display_name": "دکتر جلسه", "user_id": cons_user_id},
        headers=ahok,
    ).json()["data"]["id"]
    enc = client.post(
        "/api/v1/encounters",
        json={
            "record_id": record["id"],
            "consultant_id": cid,
            "start_at": "2025-06-21T10:00:00Z",
            "end_at": "2025-06-21T10:45:00Z",
        },
        headers=ahok,
    ).json()["data"]
    return ahok, phok, h(cons_token), record, cid, enc["id"]


def test_encounter_status_lifecycle_and_monitoring_separation():
    ahok, phok, chok, record, cid, enc_id = _base()
    # invalid transition
    bad = client.post(
        f"/api/v1/encounters/{enc_id}/status", json={"status": "completed"},
        headers=ahok,
    )
    assert bad.status_code == 409
    assert bad.json()["errors"][0]["code"] == "INVALID_TRANSITION"
    ok1 = client.post(
        f"/api/v1/encounters/{enc_id}/status", json={"status": "in_progress"},
        headers=ahok,
    )
    assert ok1.json()["data"]["status"] == "in_progress"
    ok2 = client.post(
        f"/api/v1/encounters/{enc_id}/status", json={"status": "completed"},
        headers=ahok,
    )
    assert ok2.json()["data"]["status"] == "completed"
    # patient can VIEW status but cannot post notes
    view = client.get(f"/api/v1/encounters/{enc_id}", headers=phok)
    assert view.status_code == 200
    assert view.json()["data"]["status"] == "completed"


def test_note_flow_edit_confirm_freeze_amend():
    ahok, phok, chok, record, cid, enc_id = _base()
    # only session consultant writes
    denied = client.post(
        f"/api/v1/encounters/{enc_id}/notes", json={"body": "تلاش پذیرش"}, headers=ahok
    )
    assert denied.status_code == 403
    created = client.post(
        f"/api/v1/encounters/{enc_id}/notes",
        json={"body": "مشاهده اولیه: اضطراب خفیف"},
        headers=chok,
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["data"]["id"]
    # edit while unconfirmed
    edited = client.patch(
        f"/api/v1/notes/{note_id}", json={"body": "مشاهده اولیه: اضطراب خفیف تا متوسط"},
        headers=chok,
    )
    assert edited.status_code == 200
    # confirm -> freeze
    confirmed = client.post(f"/api/v1/notes/{note_id}/confirm", headers=chok)
    assert confirmed.status_code == 200
    # direct edit after confirm -> 409 with amendment path
    frozen = client.patch(
        f"/api/v1/notes/{note_id}", json={"body": "هک"}, headers=chok
    )
    assert frozen.status_code == 409
    assert frozen.json()["errors"][0]["code"] == "NOTE_CONFIRMED"
    # amendment appends
    amend = client.post(
        f"/api/v1/notes/{note_id}/amendments",
        json={"reason": "اصلاح برداشت بالینی", "body": "اضطراب متوسط با نشانه‌های خواب"},
        headers=chok,
    )
    assert amend.status_code == 201, amend.text
    # original body unchanged in listing
    notes = client.get(f"/api/v1/encounters/{enc_id}/notes", headers=chok).json()["data"]
    target = next(n for n in notes if n["id"] == note_id)
    assert target["body"] == "مشاهده اولیه: اضطراب خفیف تا متوسط"
    assert target["confirmed"] is True
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM audit.access_events "
                "WHERE action = 'clinical.note.amend' AND resource_id = :nid"
            ),
            {"nid": UUID(note_id)},
        ).scalar_one()
    assert n >= 1


def test_patient_reads_own_session_notes():
    ahok, phok, chok, record, cid, enc_id = _base()
    client.post(
        f"/api/v1/encounters/{enc_id}/notes",
        json={"body": "یادداشت جلسه اول"},
        headers=chok,
    )
    notes = client.get(f"/api/v1/encounters/{enc_id}/notes", headers=phok)
    assert notes.status_code == 200
    assert len(notes.json()["data"]) == 1


def test_outsider_blocked_everywhere():
    ahok, phok, chok, record, cid, enc_id = _base()
    outsider_token, _ = login(_phone())
    ohok = h(outsider_token)
    assert client.get(f"/api/v1/encounters/{enc_id}", headers=ohok).status_code == 403
    assert client.get(
        f"/api/v1/encounters/{enc_id}/notes", headers=ohok
    ).status_code == 403
    assert client.post(
        f"/api/v1/encounters/{enc_id}/notes", json={"body": "نفوذ"}, headers=ohok
    ).status_code == 403
