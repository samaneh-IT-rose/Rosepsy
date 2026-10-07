from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.db import SessionLocal
from tests.helpers import client, denied_count, grant, grant_scoped, h, login

PHONE = iter(range(9141140000, 9141149999))


def _phone() -> str:
    return "0" + str(next(PHONE))


# ---------- B06: specialties and services ----------


def test_specialty_create_requires_permission_and_audits_denial():
    token, uid = login(_phone())
    resp = client.post(
        "/api/v1/specialties", json={"name": "روان‌درمانی", "slug": "psychotherapy"},
        headers=h(token),
    )
    assert resp.status_code == 403
    assert denied_count(uid, "permission:services.manage") == 1


def test_service_duration_must_be_positive():
    token, _ = grant(_phone(), "system_admin")
    resp = client.post(
        "/api/v1/services",
        json={"name": "جلسه فردی", "duration_minutes": 0},
        headers=h(token),
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"] == "duration_minutes"


def test_service_list_shows_active_only_by_default():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    created = client.post(
        "/api/v1/services",
        json={"name": "جلسه زوج‌درمانی", "duration_minutes": 60},
        headers=hok,
    )
    assert created.status_code == 201
    sid = created.json()["data"]["id"]
    client.patch(f"/api/v1/services/{sid}", json={"is_active": False}, headers=hok)
    active = client.get("/api/v1/services", headers=hok)
    assert all(s["id"] != sid for s in active.json()["data"])
    everything = client.get("/api/v1/services?include_inactive=true", headers=hok)
    assert any(s["id"] == sid for s in everything.json()["data"])


# ---------- B05: consultants and eligibility ----------


def test_new_consultant_is_not_bookable():
    token, _ = grant(_phone(), "system_admin")
    created = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر سارا محمدی"}, headers=h(token)
    )
    assert created.status_code == 201
    assert created.json()["data"]["status"] == "pending_review"
    bookable = client.get("/api/v1/consultants", headers=h(token))
    assert bookable.json()["data"] == []


def test_credential_approval_makes_consultant_bookable():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر امیر کاویانی"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={
            "kind": "license",
            "title": "پروانه نظام روان‌شناسی",
            "license_number": "LIC-1001",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        },
        headers=hok,
    )
    assert cred.status_code == 201
    review = client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred.json()["data"]["id"], "decision": "approved"},
        headers=hok,
    )
    assert review.status_code == 201
    assert review.json()["data"]["booking_eligible"] is True
    bookable = client.get("/api/v1/consultants", headers=hok)
    assert [c["id"] for c in bookable.json()["data"]] == [cid]


def test_rejected_credential_keeps_consultant_unbookable():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر نادر فرهمند"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={"kind": "certificate", "title": "گواهی CBT", "license_number": "CRT-7"},
        headers=hok,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "rejected"},
        headers=hok,
    )
    bookable = client.get("/api/v1/consultants", headers=hok)
    assert bookable.json()["data"] == []


def test_expired_credential_makes_consultant_unbookable():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر لیلا نوری"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={
            "kind": "license",
            "title": "پروانه منقضی",
            "license_number": "LIC-EXP",
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        headers=hok,
    ).json()["data"]["id"]
    review = client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "approved"},
        headers=hok,
    )
    assert review.json()["data"]["booking_eligible"] is False


def test_review_requires_permission():
    token, _ = login(_phone())
    resp = client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": str(UUID(int=99)), "decision": "approved"},
        headers=h(token),
    )
    assert resp.status_code == 403


def test_consultant_linked_to_user_gets_consultant_role():
    admin_token, _ = grant(_phone(), "system_admin")
    user_token, user_id = login(_phone())
    created = client.post(
        "/api/v1/consultants",
        json={"display_name": "دکتر مریم راد", "user_id": user_id},
        headers=h(admin_token),
    )
    assert created.status_code == 201
    me = client.get("/api/v1/me", headers=h(user_token))
    assert "consultant" in me.json()["data"]["roles"]


# ---------- B31: clinics and branches ----------


def test_clinic_slug_must_be_unique():
    token, _ = grant(_phone(), "system_admin")
    body = {"name": "کلینیک رز", "slug": "roz-main"}
    first = client.post("/api/v1/clinics", json=body, headers=h(token))
    assert first.status_code == 201
    second = client.post("/api/v1/clinics", json=body, headers=h(token))
    assert second.status_code == 409


def test_branch_lat_lon_out_of_range_rejected():
    token, _ = grant(_phone(), "system_admin")
    clinic_id = client.post(
        "/api/v1/clinics", json={"name": "کلینیک رز ۲", "slug": "roz-two"},
        headers=h(token),
    ).json()["data"]["id"]
    resp = client.post(
        f"/api/v1/clinics/{clinic_id}/branches",
        json={"name": "شعبه مرکزی", "slug": "roz-two-b1", "lat": 95, "lon": 51.4},
        headers=h(token),
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_draft_branch_not_public_until_published():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    clinic_id = client.post(
        "/api/v1/clinics", json={"name": "کلینیک رز ۳", "slug": "roz-three"},
        headers=hok,
    ).json()["data"]["id"]
    bid = client.post(
        f"/api/v1/clinics/{clinic_id}/branches",
        json={
            "name": "شعبه سعادت‌آباد", "slug": "roz-three-b1", "city": "تهران",
            "lat": 35.78, "lon": 51.37,
        },
        headers=hok,
    ).json()["data"]["id"]
    assert client.get("/api/v1/public/branches").json()["data"] == []
    pub = client.patch(f"/api/v1/branches/{bid}", json={"status": "published"}, headers=hok)
    assert pub.status_code == 200
    public = client.get("/api/v1/public/branches")
    assert [b["id"] for b in public.json()["data"]] == [bid]


def test_public_branches_city_filter():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    clinic_id = client.post(
        "/api/v1/clinics", json={"name": "کلینیک رز ۴", "slug": "roz-four"},
        headers=hok,
    ).json()["data"]["id"]
    for slug, city in (("roz-four-sh", "شیراز"), ("roz-four-th", "تهران")):
        bid = client.post(
            f"/api/v1/clinics/{clinic_id}/branches",
            json={"name": f"شعبه {city}", "slug": slug, "city": city,
                  "lat": 29.6, "lon": 52.5},
            headers=hok,
        ).json()["data"]["id"]
        client.patch(f"/api/v1/branches/{bid}", json={"status": "published"}, headers=hok)
    result = client.get("/api/v1/public/branches?city=تهران")
    data = result.json()["data"]
    assert len(data) == 1 and data[0]["city"] == "تهران"


def test_branch_shows_only_offered_and_active_services():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    clinic_id = client.post(
        "/api/v1/clinics", json={"name": "کلینیک رز ۵", "slug": "roz-five"},
        headers=hok,
    ).json()["data"]["id"]
    bid = client.post(
        f"/api/v1/clinics/{clinic_id}/branches",
        json={"name": "شعبه یک", "slug": "roz-five-b1", "lat": 35.7, "lon": 51.4,
              "status": "published"},
        headers=hok,
    ).json()["data"]["id"]
    s1 = client.post(
        "/api/v1/services", json={"name": "جلسه فردی", "duration_minutes": 45},
        headers=hok,
    ).json()["data"]["id"]
    s2 = client.post(
        "/api/v1/services", json={"name": "جلسه خانواده", "duration_minutes": 60},
        headers=hok,
    ).json()["data"]["id"]
    assert (
        client.put(f"/api/v1/branches/{bid}/services",
                   json={"service_ids": [s1]}, headers=hok).status_code
        == 200
    )
    offered = client.get(f"/api/v1/branches/{bid}/services", headers=hok).json()["data"]
    assert [s["id"] for s in offered] == [s1]  # s2 not offered -> not shown
    client.patch(f"/api/v1/services/{s1}", json={"is_active": False}, headers=hok)
    assert client.get(f"/api/v1/branches/{bid}/services", headers=hok).json()["data"] == []


def test_scoped_branch_admin_cannot_edit_other_branch():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    clinic_id = client.post(
        "/api/v1/clinics", json={"name": "کلینیک رز ۶", "slug": "roz-six"},
        headers=hok,
    ).json()["data"]["id"]
    b1 = client.post(
        f"/api/v1/clinics/{clinic_id}/branches",
        json={"name": "شعبه الف", "slug": "roz-six-a", "lat": 1.0, "lon": 1.0},
        headers=hok,
    ).json()["data"]["id"]
    b2 = client.post(
        f"/api/v1/clinics/{clinic_id}/branches",
        json={"name": "شعبه ب", "slug": "roz-six-b", "lat": 2.0, "lon": 2.0},
        headers=hok,
    ).json()["data"]["id"]
    scoped_token, scoped_uid = grant_scoped(_phone(), "system_admin", UUID(b1))
    denied = client.patch(
        f"/api/v1/branches/{b2}", json={"status": "published"}, headers=h(scoped_token)
    )
    assert denied.status_code == 403
    assert denied_count(scoped_uid, "branches.manage:scope") == 1
    allowed = client.patch(
        f"/api/v1/branches/{b1}", json={"status": "published"}, headers=h(scoped_token)
    )
    assert allowed.status_code == 200
    # global admin (branch_id NULL grant) can edit any branch
    assert client.patch(
        f"/api/v1/branches/{b2}", json={"status": "published"}, headers=hok
    ).status_code == 200
