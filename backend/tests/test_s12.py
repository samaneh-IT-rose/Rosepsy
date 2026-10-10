import pytest
from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h, login

PHONE = iter(range(9141220000, 9141229999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _grant_consent(hok, kind="treatment", channel="web"):
    return client.post(
        "/api/v1/consents", json={"kind": kind, "channel": channel}, headers=hok
    )


def test_grant_consent_snapshots_version_and_ip():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    r = _grant_consent(hok)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["active"] is True
    assert data["version"]["kind"] == "treatment"
    assert data["version"]["version"] == 1
    assert "حقوقی" in data["version"]["text_fa"]  # version text attached
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.consents import Consent

    with SessionLocal() as db:
        row = db.execute(
            select(Consent).where(Consent.id == data["id"])
        ).scalar_one()
        assert row.ip == "testclient"  # device/IP captured per spec


def test_consent_history_shows_version_text_and_dates():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    granted = _grant_consent(hok).json()["data"]
    listing = client.get("/api/v1/consents", headers=hok)
    assert listing.status_code == 200
    rows = [x for x in listing.json()["data"] if x["id"] == granted["id"]]
    assert len(rows) == 1
    row = rows[0]
    assert row["version"]["text_fa"]
    assert row["granted_at"]
    assert row["revoked_at"] is None and row["active"] is True


def test_duplicate_active_consent_409():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    assert _grant_consent(hok, kind="marketing").status_code == 201
    dup = _grant_consent(hok, kind="marketing")
    assert dup.status_code == 409
    assert dup.json()["errors"][0]["code"] == "CONSENT_ALREADY_ACTIVE"


def test_revoke_blocks_future_and_keeps_history():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    first = _grant_consent(hok).json()["data"]
    rev = client.post(f"/api/v1/consents/{first['id']}/revoke", headers=hok)
    assert rev.status_code == 200
    assert rev.json()["data"]["active"] is False
    # history preserved
    listing = client.get("/api/v1/consents", headers=hok).json()["data"]
    old = next(x for x in listing if x["id"] == first["id"])
    assert old["active"] is False and old["revoked_at"]
    # future grant allowed again
    second = _grant_consent(hok)
    assert second.status_code == 201
    # double revoke
    again = client.post(f"/api/v1/consents/{first['id']}/revoke", headers=hok)
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "CONSENT_ALREADY_REVOKED"


def test_revoke_other_users_consent_404():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    created = _grant_consent(hok).json()["data"]
    other_token, _ = login(_phone())
    resp = client.post(
        f"/api/v1/consents/{created['id']}/revoke", headers=h(other_token)
    )
    assert resp.status_code == 404


def test_unknown_kind_404():
    token, _ = grant(_phone(), "system_admin")
    resp = _grant_consent(h(token), kind="bogus_kind")
    assert resp.status_code == 404
    assert resp.json()["errors"][0]["code"] == "CONSENT_KIND_NOT_FOUND"


def test_consent_versions_are_immutable():
    """DB trigger must reject UPDATE and DELETE on consent_versions."""
    grant(_phone(), "system_admin")  # ensures consent_versions are seeded
    with pytest.raises(Exception):  # noqa: B017 - psycopg raises generic DatabaseError
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE core.consent_versions SET text_fa = 'hacked'")
            )
    with pytest.raises(Exception):  # noqa: B017 - psycopg raises generic DatabaseError
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM core.consent_versions"))


def test_new_version_used_for_new_grants_old_kept():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    v1_grant = _grant_consent(hok).json()["data"]
    assert v1_grant["version"]["version"] == 1
    v2 = client.post(
        "/api/v1/consent-versions",
        json={
            "kind": "treatment",
            "title_fa": "رضایت درمان - نسخه ۲",
            "text_fa": "متن نسخه دوم رضایت درمان با تغییرات حقوقی.",
        },
        headers=hok,
    )
    assert v2.status_code == 201, v2.text
    assert v2.json()["data"]["version"] == 2
    v2_grant = _grant_consent(hok, channel="mobile")
    # active consent exists -> revoke first, then re-grant picks v2
    assert v2_grant.status_code == 409
    client.post(f"/api/v1/consents/{v1_grant['id']}/revoke", headers=hok)
    v2_grant = _grant_consent(hok, channel="mobile")
    assert v2_grant.status_code == 201
    assert v2_grant.json()["data"]["version"]["version"] == 2
    # old consent still shows its own v1 text (history intact)
    listing = client.get("/api/v1/consents", headers=hok).json()["data"]
    old = next(x for x in listing if x["id"] == v1_grant["id"])
    assert old["version"]["version"] == 1


def test_audit_access_dpo_only_and_denied_rows():
    # plain user denied -> recorded
    plain_token, _ = login(_phone())
    denied = client.get("/api/v1/audit/access", headers=h(plain_token))
    assert denied.status_code == 403
    # DPO can read the report and sees the denial row
    dpo_token, _ = grant(_phone(), "auditor_dpo")
    report = client.get("/api/v1/audit/access", headers=h(dpo_token))
    assert report.status_code == 200, report.text
    rows = report.json()["data"]
    assert report.json()["meta"]["total"] >= 1
    assert any(
        r["action"] == "permission:audit.access.read" and r["actor_user_id"]
        for r in rows
    )


def test_create_version_requires_permission():
    token, _ = login(_phone())
    resp = client.post(
        "/api/v1/consent-versions",
        json={"kind": "treatment", "title_fa": "بدون مجوز", "text_fa": "متن آزمایشی بدون مجوز."},
        headers=h(token),
    )
    assert resp.status_code == 403
