"""B35 — Course sales: free direct, paid via gateway, exactly-one access."""

import uuid

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h
from tests.test_b34 import _add_lesson, _add_module, _mk_course

PHONE = iter(range(9142100000, 9142109999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _file_id() -> str:
    from tests.test_b34 import _file

    _, uid = grant(_phone(), "consultant")
    return _file(uid)


def _published_course(hok, *, is_free: bool, price: int = 0) -> dict:
    c = _mk_course(hok, slug=f"enr-{uuid.uuid4().hex[:8]}", is_free=is_free, price=price)
    m = _add_module(hok, c["id"])
    _add_lesson(hok, m["id"], file_id=_file_id())
    r = client.post(f"/api/v1/courses/{c['id']}/publish", headers=hok)
    assert r.status_code == 200, r.text
    return c


def test_free_enrollment_direct_and_idempotent():
    cm, _ = grant(_phone(), "content_manager")
    hc = h(cm)
    user, _ = grant(_phone(), "consultant")
    hok = h(user)
    c = _published_course(hc, is_free=True)

    r1 = client.post(f"/api/v1/courses/{c['id']}/enrollments", headers=hok)
    assert r1.status_code == 201, r1.text
    assert r1.json()["data"]["status"] == "active"
    assert r1.json()["data"]["already_enrolled"] is False

    # duplicate request -> same enrollment, no duplicate access
    r2 = client.post(f"/api/v1/courses/{c['id']}/enrollments", headers=hok)
    assert r2.status_code == 201
    assert r2.json()["data"]["already_enrolled"] is True
    assert r2.json()["data"]["enrollment_id"] == r1.json()["data"]["enrollment_id"]

    my = client.get("/api/v1/my-courses", headers=hok).json()["data"]
    mine = [x for x in my if x["course_id"] == c["id"]]
    assert len(mine) == 1
    assert mine[0]["status"] == "active"

    # direct DB check of grant count
    with engine.begin() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM edu.access_grants g "
                "JOIN core.users u ON u.id = g.user_id "
                "WHERE g.course_id = :c"
            ),
            {"c": uuid.UUID(c["id"])},
        ).scalar_one()
    assert n == 1


def test_paid_enrollment_flow_via_gateway():
    cm, _ = grant(_phone(), "content_manager")
    hc = h(cm)
    user, _ = grant(_phone(), "consultant")
    hok = h(user)
    c = _published_course(hc, is_free=False, price=1500000)

    r = client.post(f"/api/v1/courses/{c['id']}/enrollments", headers=hok)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["status"] == "pending_payment"
    order_id = data["order_id"]
    assert order_id

    # before payment: no access to lessons
    detail = client.get(f"/api/v1/public/courses/{c['slug']}", headers=hok).json()["data"]
    assert detail["enrolled"] is False

    start = client.post(
        "/api/v1/payments/start", json={"order_id": order_id}, headers=hok
    ).json()["data"]
    cb = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    assert cb.status_code == 200, cb.text
    assert cb.json()["data"]["fulfillment"]["activated"] is True

    # after payment: active + exactly one grant + invoice
    my = client.get("/api/v1/my-courses", headers=hok).json()["data"]
    mine = [x for x in my if x["course_id"] == c["id"]]
    assert mine[0]["status"] == "active"

    detail2 = client.get(f"/api/v1/public/courses/{c['slug']}", headers=hok).json()["data"]
    assert detail2["enrolled"] is True
    assert detail2["modules"][0]["lessons"][0]["file_accessible"] is True

    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM edu.access_grants WHERE course_id = :c"),
            {"c": uuid.UUID(c["id"])},
        ).scalar_one()
        inv = conn.execute(
            text(
                "SELECT count(*) FROM finance.invoices i "
                "JOIN finance.orders o ON o.id = i.order_id WHERE o.id = :o"
            ),
            {"o": uuid.UUID(order_id)},
        ).scalar_one()
    assert n == 1
    assert inv == 1

    # re-enrollment after payment is idempotent
    r3 = client.post(f"/api/v1/courses/{c['id']}/enrollments", headers=hok)
    assert r3.json()["data"]["already_enrolled"] is True


def test_progress_requires_access():
    cm, _ = grant(_phone(), "content_manager")
    hc = h(cm)
    user, _ = grant(_phone(), "consultant")
    hok = h(user)
    c = _published_course(hc, is_free=False, price=700000)
    detail = client.get(f"/api/v1/public/courses/{c['slug']}", headers=hok).json()["data"]
    lesson_id = detail["modules"][0]["lessons"][0]["id"]

    denied = client.post(f"/api/v1/lessons/{lesson_id}/progress", headers=hok)
    assert denied.status_code == 403

    # enroll free... it's paid; enroll via gateway then mark progress
    enr = client.post(f"/api/v1/courses/{c['id']}/enrollments", headers=hok).json()["data"]
    start = client.post(
        "/api/v1/payments/start", json={"order_id": enr["order_id"]}, headers=hok
    ).json()["data"]
    client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    ok = client.post(f"/api/v1/lessons/{lesson_id}/progress", headers=hok)
    assert ok.status_code == 201, ok.text

    my = client.get("/api/v1/my-courses", headers=hok).json()["data"]
    mine = [x for x in my if x["course_id"] == c["id"]][0]
    assert mine["progress"]["completed_lessons"] == 1
    assert mine["progress"]["total_lessons"] == 1
