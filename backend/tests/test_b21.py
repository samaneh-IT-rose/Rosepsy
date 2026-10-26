"""B21 — Organizations: contracts, member validity at service time."""

import uuid
from datetime import UTC, datetime, timedelta

from tests.helpers import client, grant, h

PHONE = iter(range(9142040000, 9142049999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _org(hok, **kw) -> dict:
    body = {
        "name": kw.pop("name", "شرکت نمونه"),
        "national_id": kw.pop("national_id", f"NT-{uuid.uuid4().hex[:10]}"),
    }
    body.update(kw)
    r = client.post("/api/v1/organizations", json=body, headers=hok)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_organization_crud_and_duplicate_national_id():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    org = _org(hok)
    assert org["is_active"] is True

    dup = client.post(
        "/api/v1/organizations",
        json={"name": "تکراری", "national_id": org["national_id"]},
        headers=hok,
    )
    assert dup.status_code == 409

    # non-manager denied
    user, _ = grant(_phone(), "consultant")
    denied = client.post(
        "/api/v1/organizations",
        json={"name": "غیرمجاز", "national_id": f"X-{uuid.uuid4().hex[:8]}"},
        headers=h(user),
    )
    assert denied.status_code == 403

    detail = client.get(f"/api/v1/organizations/{org['id']}", headers=hok)
    assert detail.status_code == 200
    assert detail.json()["data"]["members"] == []


def test_member_add_end_and_validity():
    admin, _ = grant(_phone(), "system_admin")
    hok = h(admin)
    user, user_id = grant(_phone(), "consultant")
    org = _org(hok)

    # contract
    c = client.post(
        f"/api/v1/organizations/{org['id']}/contracts",
        json={
            "title": "قرارداد سالانه",
            "share_percent": 30,
            "valid_from": "2024-01-01T00:00:00Z",
        },
        headers=hok,
    )
    assert c.status_code == 201, c.text
    assert c.json()["data"]["share_percent"] == 30.0

    # invalid window
    bad = client.post(
        f"/api/v1/organizations/{org['id']}/contracts",
        json={
            "title": "نامعتبر",
            "share_percent": 10,
            "valid_from": "2024-05-01T00:00:00Z",
            "valid_to": "2024-04-01T00:00:00Z",
        },
        headers=hok,
    )
    assert bad.status_code == 422

    # add member
    m = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": user_id, "valid_days": 30},
        headers=hok,
    )
    assert m.status_code == 201, m.text

    # duplicate active membership rejected (even in another org)
    org2 = _org(hok)
    dup = client.post(
        f"/api/v1/organizations/{org2['id']}/members",
        json={"user_id": user_id},
        headers=hok,
    )
    assert dup.status_code == 409

    detail = client.get(f"/api/v1/organizations/{org['id']}", headers=hok).json()["data"]
    assert len(detail["members"]) == 1
    assert detail["members"][0]["user_id"] == user_id

    # end membership
    end = client.delete(
        f"/api/v1/organizations/{org['id']}/members/{user_id}", headers=hok
    )
    assert end.status_code == 200
    assert end.json()["data"]["ended"] is True

    # after ending, user can join another org
    m2 = client.post(
        f"/api/v1/organizations/{org2['id']}/members",
        json={"user_id": user_id},
        headers=hok,
    )
    assert m2.status_code == 201, m2.text


def test_membership_validity_service_check():
    from app.core.db import SessionLocal
    from app.services.organizations import is_active_member

    admin, _ = grant(_phone(), "system_admin")
    hok = h(admin)
    user, user_id = grant(_phone(), "consultant")
    org = _org(hok)
    client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": user_id, "valid_days": 7},
        headers=hok,
    )
    with SessionLocal() as db:
        now_member = is_active_member(db, uuid.UUID(user_id))
        assert now_member is not None
        future = is_active_member(
            db, uuid.UUID(user_id), at=datetime.now(UTC) + timedelta(days=30)
        )
        assert future is None
