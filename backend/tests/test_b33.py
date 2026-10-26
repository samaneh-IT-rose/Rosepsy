"""B33 — CMS: draft never public, review flow, revisions, topic filter, search."""

import uuid

from tests.helpers import client, grant, h

PHONE = iter(range(9142080000, 9142089999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _mk_content(hok, **kw) -> dict:
    body = {
        "type": kw.pop("type", "article"),
        "title": kw.pop("title", "راهنمای سلامت روان"),
        "body": kw.pop("body", "متن کامل مقاله برای مخاطب عمومی."),
    }
    body.update(kw)
    r = client.post("/api/v1/contents", json=body, headers=hok)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_draft_not_public_and_full_flow():
    cm, _ = grant(_phone(), "content_manager")
    hok = h(cm)
    c = _mk_content(hok, slug=f"guide-{uuid.uuid4().hex[:8]}")

    # draft is NOT public
    pub = client.get("/api/v1/public/contents")
    assert all(x["slug"] != c["slug"] for x in pub.json()["data"])
    detail = client.get(f"/api/v1/public/contents/{c['slug']}")
    assert detail.status_code == 404

    # manager sees it in the management list
    managed = client.get("/api/v1/contents", headers=hok).json()["data"]
    assert any(x["id"] == c["id"] for x in managed)

    # publish directly from draft is invalid (must go through review)
    skip = client.post(f"/api/v1/contents/{c['id']}/publish", headers=hok)
    assert skip.status_code == 409

    rv = client.post(f"/api/v1/contents/{c['id']}/submit-review", headers=hok)
    assert rv.json()["data"]["status"] == "in_review"
    p = client.post(f"/api/v1/contents/{c['id']}/publish", headers=hok)
    assert p.status_code == 200, p.text
    assert p.json()["data"]["status"] == "published"
    assert p.json()["data"]["published_at"] is not None

    # now public
    pub2 = client.get("/api/v1/public/contents").json()["data"]
    assert any(x["slug"] == c["slug"] for x in pub2)
    det2 = client.get(f"/api/v1/public/contents/{c['slug']}")
    assert det2.status_code == 200
    assert det2.json()["data"]["body"] is not None

    # archive -> back to public-visibility off
    ar = client.post(f"/api/v1/contents/{c['id']}/archive", headers=hok)
    assert ar.json()["data"]["status"] == "archived"
    pub3 = client.get("/api/v1/public/contents").json()["data"]
    assert all(x["slug"] != c["slug"] for x in pub3)


def test_revisions_history():
    cm, _ = grant(_phone(), "content_manager")
    hok = h(cm)
    c = _mk_content(hok, title="نسخه اول مقاله")
    u = client.put(
        f"/api/v1/contents/{c['id']}",
        json={
            "type": "article",
            "title": "نسخه دوم مقاله",
            "body": "متن ویرایش‌شده.",
        },
        headers=hok,
    )
    assert u.status_code == 200, u.text
    detail = client.get(f"/api/v1/contents/{c['id']}", headers=hok).json()["data"]
    versions = [r["version"] for r in detail["revisions"]]
    assert versions == sorted(versions, reverse=True)
    assert len(versions) >= 2
    v1 = next(r for r in detail["revisions"] if r["version"] == 1)
    assert v1["snapshot"]["title"] == "نسخه اول مقاله"


def test_topic_filter_and_search_public():
    admin, _ = grant(_phone(), "system_admin")
    hadmin = h(admin)
    topic = client.post(
        "/api/v1/topics",
        json={"name": f"اضطراب-{uuid.uuid4().hex[:6]}", "slug": f"anx-{uuid.uuid4().hex[:8]}"},
        headers=hadmin,
    ).json()["data"]
    cm, _ = grant(_phone(), "content_manager")
    hok = h(cm)
    marker = uuid.uuid4().hex[:8]
    c = _mk_content(
        hok,
        title=f"مقاله اضطراب {marker}",
        topic_ids=[topic["id"]],
    )
    client.post(f"/api/v1/contents/{c['id']}/submit-review", headers=hok)
    client.post(f"/api/v1/contents/{c['id']}/publish", headers=hok)

    by_topic = client.get(
        f"/api/v1/public/contents?topic_id={topic['id']}"
    ).json()["data"]
    assert any(x["slug"] == c["slug"] for x in by_topic)

    by_search = client.get(f"/api/v1/public/contents?q={marker}").json()["data"]
    assert any(x["slug"] == c["slug"] for x in by_search)


def test_permission_required_for_management():
    user, _ = grant(_phone(), "consultant")
    denied = client.post(
        "/api/v1/contents",
        json={"type": "news", "title": "خبر غیرمجاز"},
        headers=h(user),
    )
    assert denied.status_code == 403
    denied2 = client.get("/api/v1/contents", headers=h(user))
    assert denied2.status_code == 403
