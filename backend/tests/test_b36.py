"""B36 — Course exams & certificates: server scoring, attempt cap, unique certificate."""

import uuid

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h
from tests.test_b35 import _published_course

PHONE = iter(range(9142110000, 9142119999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _exam_with_questions(hok, course_id: str, *, pass_score=60, max_attempts=1) -> dict:
    e = client.post(
        f"/api/v1/courses/{course_id}/exams",
        json={
            "title": "آزمون پایان دوره",
            "pass_score": pass_score,
            "max_attempts": max_attempts,
        },
        headers=hok,
    )
    assert e.status_code == 201, e.text
    exam = e.json()["data"]
    q1 = client.post(
        f"/api/v1/course-exams/{exam['id']}/questions",
        json={"text": "۲+۲ چند است؟", "options": ["۳", "۴", "۵"], "correct_index": 1, "weight": 1},
        headers=hok,
    )
    assert q1.status_code == 201, q1.text
    q2 = client.post(
        f"/api/v1/course-exams/{exam['id']}/questions",
        json={
            "text": "پایتخت ایران؟",
            "options": ["تهران", "شیراز"],
            "correct_index": 0,
            "weight": 3,
        },
        headers=hok,
    )
    assert q2.status_code == 201, q2.text
    return exam


def _enroll_paid(hok, course_id: str) -> None:
    enr = client.post(f"/api/v1/courses/{course_id}/enrollments", headers=hok).json()["data"]
    if enr["status"] == "pending_payment":
        start = client.post(
            "/api/v1/payments/start", json={"order_id": enr["order_id"]}, headers=hok
        ).json()["data"]
        cb = client.post(
            "/api/v1/payments/callback",
            json={"gateway_ref": start["gateway_ref"], "result": "success"},
            headers=hok,
        )
        assert cb.status_code == 200, cb.text


def test_exam_requires_enrollment():
    cm, _ = grant(_phone(), "content_manager")
    hc = h(cm)
    user, _ = grant(_phone(), "consultant")
    hok = h(user)
    c = _published_course(hc, is_free=True)
    exam = _exam_with_questions(hc, c["id"])

    denied = client.post(f"/api/v1/course-exams/{exam['id']}/attempts", headers=hok)
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["code"] == "NO_ACCESS"


def test_scoring_pass_and_certificate_once():
    cm, _ = grant(_phone(), "content_manager")
    hc = h(cm)
    user, _ = grant(_phone(), "consultant")
    hok = h(user)
    c = _published_course(hc, is_free=True)
    exam = _exam_with_questions(hc, c["id"], pass_score=60)

    _enroll_paid(hok, c["id"])

    attempt = client.post(
        f"/api/v1/course-exams/{exam['id']}/attempts", headers=hok
    ).json()["data"]
    aid = attempt["attempt_id"]

    # fetch question ids from DB (questions are never exposed to clients)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, correct_index FROM edu.exam_questions WHERE exam_id = :e "
                "ORDER BY position"
            ),
            {"e": uuid.UUID(exam["id"])},
        ).all()
    questions = {}
    for qid, correct in rows:
        questions[str(qid)] = correct

    answers = [
        {"question_id": qid, "selected_index": correct}
        for qid, correct in questions.items()
    ]
    sub = client.post(
        f"/api/v1/course-attempts/{aid}/submit", json={"answers": answers}, headers=hok
    )
    assert sub.status_code == 200, sub.text
    data = sub.json()["data"]
    assert data["status"] == "passed"
    assert data["score"] == 100
    assert data["certificate_number"] is not None

    # certificate exactly once in DB
    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM edu.certificates WHERE exam_attempt_id = :a"),
            {"a": uuid.UUID(aid)},
        ).scalar_one()
    assert n == 1

    # resubmit same attempt rejected
    sub2 = client.post(
        f"/api/v1/course-attempts/{aid}/submit", json={"answers": answers}, headers=hok
    )
    assert sub2.status_code == 409

    # my certificates + public verify
    mine = client.get("/api/v1/my-certificates", headers=hok).json()["data"]
    assert len(mine) == 1
    code = mine[0]["verification_code"]
    v = client.get(f"/api/v1/certificates/verify/{code}")
    assert v.status_code == 200, v.text
    assert v.json()["data"]["valid"] is True
    assert "****" in v.json()["data"]["holder_masked"]

    v404 = client.get("/api/v1/certificates/verify/deadbeef")
    assert v404.status_code == 404


def test_fail_then_attempt_cap():
    cm, _ = grant(_phone(), "content_manager")
    hc = h(cm)
    user, _ = grant(_phone(), "consultant")
    hok = h(user)
    c = _published_course(hc, is_free=True)
    exam = _exam_with_questions(hc, c["id"], pass_score=100, max_attempts=2)

    _enroll_paid(hok, c["id"])

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, correct_index FROM edu.exam_questions WHERE exam_id = :e"),
            {"e": uuid.UUID(exam["id"])},
        ).all()

    wrong = [
        {"question_id": str(qid), "selected_index": (correct + 1) % 2}
        for qid, correct in rows
    ]
    a1 = client.post(f"/api/v1/course-exams/{exam['id']}/attempts", headers=hok).json()["data"]
    s1 = client.post(
        f"/api/v1/course-attempts/{a1['attempt_id']}/submit",
        json={"answers": wrong},
        headers=hok,
    )
    assert s1.json()["data"]["status"] == "failed"
    assert s1.json()["data"]["certificate_number"] is None

    # enrollment stays active (not completed) after failure
    my = client.get("/api/v1/my-courses", headers=hok).json()["data"]
    mine = [x for x in my if x["course_id"] == c["id"]][0]
    assert mine["status"] == "active"

    a2 = client.post(f"/api/v1/course-exams/{exam['id']}/attempts", headers=hok).json()["data"]
    s2 = client.post(
        f"/api/v1/course-attempts/{a2['attempt_id']}/submit",
        json={"answers": wrong},
        headers=hok,
    )
    assert s2.json()["data"]["status"] == "failed"

    # third attempt blocked (max_attempts=2)
    a3 = client.post(f"/api/v1/course-exams/{exam['id']}/attempts", headers=hok)
    assert a3.status_code == 409
    assert a3.json()["errors"][0]["code"] == "ATTEMPT_CAP_REACHED"
