"""B34 — Courses: price rules, publish gate, lesson versioning, progress."""

import uuid

from tests.helpers import client, grant, h

PHONE = iter(range(9142090000, 9142099999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _mk_course(hok, **kw) -> dict:
    body = {
        "title": kw.pop("title", "دوره مهارت‌های ارتباطی"),
        "is_free": kw.pop("is_free", True),
        "price": kw.pop("price", 0),
    }
    body.update(kw)
    r = client.post("/api/v1/courses", json=body, headers=hok)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _add_module(hok, course_id: str, title: str = "فصل اول") -> dict:
    r = client.post(
        f"/api/v1/courses/{course_id}/modules", json={"title": title}, headers=hok
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _add_lesson(hok, module_id: str, **kw) -> dict:
    body = {"title": kw.pop("title", "درس اول"), "file_id": kw.pop("file_id", None)}
    body.update(kw)
    r = client.post(f"/api/v1/modules/{module_id}/lessons", json=body, headers=hok)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _file(owner_id: str) -> str:
    """Create a clean File row directly (MinIO not needed for edu tests)."""
    from app.core.db import SessionLocal
    from app.models.files import File

    with SessionLocal() as db:
        f = File(
            owner_user_id=uuid.UUID(owner_id),
            context="general",
            filename=f"lesson-{uuid.uuid4().hex[:8]}.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            storage_key=f"roz-files/lesson-{uuid.uuid4().hex}.mp4",
            checksum="chk-" + uuid.uuid4().hex,
            status="clean",
        )
        db.add(f)
        db.commit()
        return str(f.id)


def test_course_price_rules():
    cm, _ = grant(_phone(), "content_manager")
    hok = h(cm)
    free_with_price = client.post(
        "/api/v1/courses",
        json={"title": "رایگان با قیمت", "is_free": True, "price": 1000},
        headers=hok,
    )
    assert free_with_price.status_code == 422
    paid_zero = client.post(
        "/api/v1/courses",
        json={"title": "پولی صفر", "is_free": False, "price": 0},
        headers=hok,
    )
    assert paid_zero.status_code == 422
    paid_ok = _mk_course(hok, is_free=False, price=1200000)
    assert paid_ok["price"] == 1200000


def test_publish_requires_valid_lesson():
    cm, cm_uid = grant(_phone(), "content_manager")
    hok = h(cm)
    c = _mk_course(hok, slug=f"gate-{uuid.uuid4().hex[:8]}")

    # no lessons at all
    denied = client.post(f"/api/v1/courses/{c['id']}/publish", headers=hok)
    assert denied.status_code == 422
    assert denied.json()["errors"][0]["code"] == "COURSE_NOT_PUBLISHABLE"

    # lesson without a file is not "valid"
    m = _add_module(hok, c["id"])
    _add_lesson(hok, m["id"], file_id=None)
    denied2 = client.post(f"/api/v1/courses/{c['id']}/publish", headers=hok)
    assert denied2.status_code == 422

    # a lesson with a file
    fid = _file(cm_uid)
    _add_lesson(hok, m["id"], title="درس ویدئویی", file_id=fid, is_preview=True)
    ok = client.post(f"/api/v1/courses/{c['id']}/publish", headers=hok)
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["status"] == "published"

    # public catalog shows it
    pub = client.get("/api/v1/public/courses").json()["data"]
    assert any(x["slug"] == c["slug"] for x in pub)


def test_published_lesson_edit_keeps_version():
    cm, cm_uid = grant(_phone(), "content_manager")
    hok = h(cm)
    c = _mk_course(hok, slug=f"ver-{uuid.uuid4().hex[:8]}")
    m = _add_module(hok, c["id"])
    fid = _file(cm_uid)
    lesson = _add_lesson(hok, m["id"], file_id=fid)
    client.post(f"/api/v1/courses/{c['id']}/publish", headers=hok)

    u = client.put(
        f"/api/v1/lessons/{lesson['id']}",
        json={"title": "درس ویرایش‌شده", "lesson_type": "video", "file_id": fid},
        headers=hok,
    )
    assert u.status_code == 200, u.text
    assert u.json()["data"]["version"] == 2

    from sqlalchemy import text as t

    from app.core.db import engine

    with engine.begin() as conn:
        n = conn.execute(
            t("SELECT count(*) FROM edu.lesson_versions WHERE lesson_id = :l"),
            {"l": uuid.UUID(lesson["id"])},
        ).scalar_one()
    assert n == 1  # previous version snapshot kept


def test_public_course_detail_hides_paid_files_until_enrolled():
    cm, cm_uid = grant(_phone(), "content_manager")
    hc = h(cm)
    c = _mk_course(hc, slug=f"paid-{uuid.uuid4().hex[:8]}", is_free=False, price=900000)
    m = _add_module(hc, c["id"])
    fid = _file(cm_uid)
    _add_lesson(hc, m["id"], file_id=fid, is_preview=False)
    client.post(f"/api/v1/courses/{c['id']}/publish", headers=hc)

    user, _ = grant(_phone(), "consultant")
    detail = client.get(f"/api/v1/public/courses/{c['slug']}", headers=h(user)).json()["data"]
    assert detail["enrolled"] is False
    assert detail["modules"][0]["lessons"][0]["file_accessible"] is False
