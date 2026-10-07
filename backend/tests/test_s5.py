from datetime import datetime, timedelta, timezone
from uuid import UUID

from tests.helpers import client, denied_count, grant, h, login

PHONE = iter(range(9141150000, 9141159999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _mk_service(hok) -> str:
    r = client.post(
        "/api/v1/services",
        json={"name": "جلسه آزمایشی تعرفه", "duration_minutes": 45},
        headers=hok,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _mk_tariff(hok, service_id: str) -> str:
    r = client.post("/api/v1/tariffs", json={"service_id": service_id}, headers=hok)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


# ---------- B07: versioned tariffs ----------


def test_tariff_create_requires_permission_and_audits_denial():
    token, uid = login(_phone())
    resp = client.post(
        "/api/v1/tariffs", json={"service_id": str(UUID(int=1))}, headers=h(token)
    )
    assert resp.status_code == 403
    assert denied_count(uid, "permission:tariffs.manage") == 1


def test_tariff_and_open_version_created():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    tid = _mk_tariff(hok, sid)
    v = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 4500000, "valid_from": _iso(datetime.now(timezone.utc) - timedelta(days=1))},
        headers=hok,
    )
    assert v.status_code == 201, v.text
    listing = client.get(f"/api/v1/tariffs?service_id={sid}", headers=hok)
    assert listing.status_code == 200
    assert listing.json()["data"][0]["versions"][0]["amount"] == 4500000


def test_overlapping_version_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    tid = _mk_tariff(hok, sid)
    now = datetime.now(timezone.utc)
    first = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={
            "amount": 100000,
            "valid_from": _iso(now - timedelta(days=5)),
            "valid_to": _iso(now + timedelta(days=5)),
        },
        headers=hok,
    )
    assert first.status_code == 201
    overlap = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 200000, "valid_from": _iso(now)},
        headers=hok,
    )
    assert overlap.status_code == 409
    assert overlap.json()["errors"][0]["code"] == "TARIFF_OVERLAP"


def test_adjacent_version_allowed():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    tid = _mk_tariff(hok, sid)
    now = datetime.now(timezone.utc)
    boundary = now + timedelta(days=5)
    v1 = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={
            "amount": 100000,
            "valid_from": _iso(now),
            "valid_to": _iso(boundary),
        },
        headers=hok,
    )
    assert v1.status_code == 201
    v2 = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 200000, "valid_from": _iso(boundary)},
        headers=hok,
    )
    assert v2.status_code == 201, v2.text  # starts exactly when v1 ends


def test_invalid_version_range_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    tid = _mk_tariff(hok, sid)
    now = datetime.now(timezone.utc)
    resp = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={
            "amount": 100000,
            "valid_from": _iso(now),
            "valid_to": _iso(now - timedelta(days=1)),
        },
        headers=hok,
    )
    assert resp.status_code == 422


def test_quote_snapshot_semantics():
    """Old price stays queryable at past instants (order snapshot premise, spec B07)."""
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    tid = _mk_tariff(hok, sid)
    now = datetime.now(timezone.utc)
    v1 = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 4500000, "valid_from": _iso(now - timedelta(days=2))},
        headers=hok,
    ).json()["data"]
    switch = now + timedelta(days=30)
    closed = client.patch(
        f"/api/v1/tariffs/{tid}/versions/{v1['id']}",
        json={"valid_to": _iso(switch)},
        headers=hok,
    )
    assert closed.status_code == 200
    v2 = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 5000000, "valid_from": _iso(switch)},
        headers=hok,
    )
    assert v2.status_code == 201

    q_now = client.get(
        "/api/v1/pricing/quote", params={"service_id": sid, "at": _iso(now)}, headers=hok
    )
    assert q_now.status_code == 200
    assert q_now.json()["data"]["amount"] == 4500000
    assert q_now.json()["data"]["version_id"] == v1["id"]

    q_future = client.get(
        "/api/v1/pricing/quote",
        params={"service_id": sid, "at": _iso(now + timedelta(days=31))},
        headers=hok,
    )
    assert q_future.json()["data"]["amount"] == 5000000

    q_before = client.get(
        "/api/v1/pricing/quote",
        params={"service_id": sid, "at": _iso(now - timedelta(days=3))},
        headers=hok,
    )
    assert q_before.status_code == 404
    assert q_before.json()["errors"][0]["code"] == "NO_APPLICABLE_VERSION"

    q_default = client.get(
        "/api/v1/pricing/quote", params={"service_id": sid}, headers=hok
    )
    assert q_default.json()["data"]["amount"] == 4500000


def test_close_enables_successor_and_double_close_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    tid = _mk_tariff(hok, sid)
    now = datetime.now(timezone.utc)
    v1 = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 100000, "valid_from": _iso(now - timedelta(days=1))},
        headers=hok,
    ).json()["data"]
    close = client.patch(
        f"/api/v1/tariffs/{tid}/versions/{v1['id']}",
        json={"valid_to": _iso(now + timedelta(days=10))},
        headers=hok,
    )
    assert close.status_code == 200
    v2 = client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 150000, "valid_from": _iso(now + timedelta(days=10))},
        headers=hok,
    )
    assert v2.status_code == 201
    again = client.patch(
        f"/api/v1/tariffs/{tid}/versions/{v1['id']}",
        json={"valid_to": _iso(now + timedelta(days=20))},
        headers=hok,
    )
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "VERSION_ALREADY_CLOSED"


def test_quote_without_tariff_404():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    sid = _mk_service(hok)
    q = client.get("/api/v1/pricing/quote", params={"service_id": sid}, headers=hok)
    assert q.status_code == 404
    assert q.json()["errors"][0]["code"] == "TARIFF_NOT_FOUND"


# ---------- B32: topic tree ----------


def test_topic_create_requires_permission():
    token, uid = login(_phone())
    resp = client.post(
        "/api/v1/topics", json={"name": "اضطراب", "slug": "anxiety"}, headers=h(token)
    )
    assert resp.status_code == 403
    assert denied_count(uid, "permission:topics.manage") == 1


def test_topic_tree_and_duplicate_slug():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    root = client.post(
        "/api/v1/topics", json={"name": "افسردگی", "slug": "depression"}, headers=hok
    )
    assert root.status_code == 201
    child = client.post(
        "/api/v1/topics",
        json={"name": "افسردگی بزرگسالان", "slug": "depression-adults",
              "parent_id": root.json()["data"]["id"]},
        headers=hok,
    )
    assert child.status_code == 201
    assert child.json()["data"]["parent_id"] == root.json()["data"]["id"]
    dup = client.post(
        "/api/v1/topics", json={"name": "تکراری", "slug": "depression"}, headers=hok
    )
    assert dup.status_code == 409
    listing = client.get("/api/v1/topics", headers=hok)
    assert listing.json()["meta"]["request_id"]
    assert len(listing.json()["data"]) == 2


def test_topic_cycle_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    a = client.post(
        "/api/v1/topics", json={"name": "A", "slug": "cyc-a"}, headers=hok
    ).json()["data"]
    b = client.post(
        "/api/v1/topics",
        json={"name": "B", "slug": "cyc-b", "parent_id": a["id"]},
        headers=hok,
    ).json()["data"]
    to_child = client.patch(f"/api/v1/topics/{a['id']}", json={"parent_id": b["id"]}, headers=hok)
    assert to_child.status_code == 409
    assert to_child.json()["errors"][0]["code"] == "TOPIC_CYCLE"
    to_self = client.patch(f"/api/v1/topics/{a['id']}", json={"parent_id": a["id"]}, headers=hok)
    assert to_self.status_code == 409


def test_topic_delete_rules():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    root = client.post(
        "/api/v1/topics", json={"name": "ریشه", "slug": "del-root"}, headers=hok
    ).json()["data"]
    leaf = client.post(
        "/api/v1/topics",
        json={"name": "برگ", "slug": "del-leaf", "parent_id": root["id"]},
        headers=hok,
    ).json()["data"]
    blocked = client.delete(f"/api/v1/topics/{root['id']}", headers=hok)
    assert blocked.status_code == 409
    assert blocked.json()["errors"][0]["code"] == "TOPIC_HAS_CHILDREN"
    ok = client.delete(f"/api/v1/topics/{leaf['id']}", headers=hok)
    assert ok.status_code == 200
    now_ok = client.delete(f"/api/v1/topics/{root['id']}", headers=hok)
    assert now_ok.status_code == 200


def test_topic_deactivate_hides_from_public():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    t = client.post(
        "/api/v1/topics", json={"name": "خواب", "slug": "sleep"}, headers=hok
    ).json()["data"]
    pub_before = client.get("/api/v1/public/topics")
    assert any(x["slug"] == "sleep" for x in pub_before.json()["data"])
    off = client.patch(f"/api/v1/topics/{t['id']}", json={"is_active": False}, headers=hok)
    assert off.status_code == 200
    pub_after = client.get("/api/v1/public/topics")
    assert all(x["slug"] != "sleep" for x in pub_after.json()["data"])
    active_only = client.get("/api/v1/topics", headers=hok)
    assert all(x["slug"] != "sleep" for x in active_only.json()["data"])
    with_inactive = client.get("/api/v1/topics?include_inactive=true", headers=hok)
    assert any(x["slug"] == "sleep" for x in with_inactive.json()["data"])


def test_public_topics_anonymous():
    token, _ = grant(_phone(), "system_admin")
    client.post(
        "/api/v1/topics", json={"name": "روابط", "slug": "relations"}, headers=h(token)
    )
    resp = client.get("/api/v1/public/topics")  # no Authorization header
    assert resp.status_code == 200
    assert any(x["slug"] == "relations" for x in resp.json()["data"])
