from zoneinfo import ZoneInfo

import httpx

from tests.helpers import client, grant, h, login

PHONE = iter(range(9141200000, 9141209999))
TZ = ZoneInfo("Asia/Tehran")
PDF_BYTES = b"%PDF-1.4 roz-test-document"


def _phone() -> str:
    return "0" + str(next(PHONE))


def _intent(hok, **overrides):
    body = {
        "filename": overrides.pop("filename", "document.pdf"),
        "content_type": overrides.pop("content_type", "application/pdf"),
        "size_bytes": overrides.pop("size_bytes", len(PDF_BYTES)),
        "context": overrides.pop("context", "general"),
        **overrides,
    }
    return client.post("/api/v1/files/upload-intents", json=body, headers=hok)


def test_intent_validates_content_type_and_size():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    bad_type = _intent(hok, content_type="application/javascript", filename="a.js")
    assert bad_type.status_code == 422
    assert bad_type.json()["errors"][0]["code"] == "CONTENT_TYPE_NOT_ALLOWED"
    too_big = _intent(hok, size_bytes=21 * 1024 * 1024)
    assert too_big.status_code == 422
    assert too_big.json()["errors"][0]["code"] == "FILE_TOO_LARGE"
    zero = _intent(hok, size_bytes=0)
    assert zero.status_code == 422  # pydantic gt=0


def test_full_clean_flow_with_real_minio():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    created = _intent(hok)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["status"] == "uploaded"
    assert data["upload_url"].startswith("http://localhost:9000/roz-files/")

    put = httpx.put(data["upload_url"], content=PDF_BYTES, timeout=10)
    assert put.status_code in (200, 201), put.text

    done = client.post(f"/api/v1/files/{data['id']}/complete", headers=hok)
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "clean"

    ticket = client.get(f"/api/v1/files/{data['id']}/download-ticket", headers=hok)
    assert ticket.status_code == 200, ticket.text
    tdata = ticket.json()["data"]
    assert tdata["expires_in_seconds"] == 60
    fetched = httpx.get(tdata["download_url"], timeout=10)
    assert fetched.status_code == 200
    assert fetched.content == PDF_BYTES


def test_virus_file_is_quarantined_and_denied():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    data = _intent(hok, filename="eicar-virus-test.pdf").json()["data"]
    assert httpx.put(data["upload_url"], content=PDF_BYTES, timeout=10).status_code in (200, 201)
    done = client.post(f"/api/v1/files/{data['id']}/complete", headers=hok)
    assert done.json()["data"]["status"] == "quarantined"
    ticket = client.get(f"/api/v1/files/{data['id']}/download-ticket", headers=hok)
    assert ticket.status_code == 409
    assert ticket.json()["errors"][0]["code"] == "FILE_QUARANTINED"


def test_complete_without_object_and_ticket_before_ready():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    data = _intent(hok).json()["data"]  # never PUT the bytes
    done = client.post(f"/api/v1/files/{data['id']}/complete", headers=hok)
    assert done.status_code == 409
    assert done.json()["errors"][0]["code"] == "OBJECT_NOT_UPLOADED"
    ticket = client.get(f"/api/v1/files/{data['id']}/download-ticket", headers=hok)
    assert ticket.status_code == 409
    assert ticket.json()["errors"][0]["code"] == "FILE_NOT_READY"


def test_foreign_user_ticket_404():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    data = _intent(hok).json()["data"]
    other_token, _ = login(_phone())
    resp = client.get(f"/api/v1/files/{data['id']}/download-ticket", headers=h(other_token))
    assert resp.status_code == 404


def test_double_complete_409():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    data = _intent(hok).json()["data"]
    assert httpx.put(data["upload_url"], content=PDF_BYTES, timeout=10).status_code in (200, 201)
    first = client.post(f"/api/v1/files/{data['id']}/complete", headers=hok)
    assert first.status_code == 200
    second = client.post(f"/api/v1/files/{data['id']}/complete", headers=hok)
    assert second.status_code == 409
    assert second.json()["errors"][0]["code"] == "INVALID_FILE_STATE"


def test_size_mismatch_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    data = _intent(hok, size_bytes=99999).json()["data"]
    httpx.put(data["upload_url"], content=PDF_BYTES, timeout=10)
    done = client.post(f"/api/v1/files/{data['id']}/complete", headers=hok)
    assert done.status_code == 409
    assert done.json()["errors"][0]["code"] == "SIZE_MISMATCH"


def test_unauthenticated_intent_rejected():
    resp = _intent({}, filename="x.pdf")
    assert resp.status_code == 401
