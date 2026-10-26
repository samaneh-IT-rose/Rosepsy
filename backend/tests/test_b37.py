"""B37 — Psychology tests and interpretation (Release 4).

Spec acceptance covered here:
- ورود و رضایت پیش از اجرا (consent gate before questions/answers)
- نسخه پاسخ‌ها ثابت (answers scored from the frozen version snapshot)
- انتشار قواعد تفسیر تنها پس از تأیید علمی (publish requires approval)
- نتیجه فرد دیگر دیده نشود (owner-only results + access_events logging)
- تفسیر قابل ردیابی به نسخه و قاعده مصوب (rule_id + snapshot text)
- state machine: started → consented → in_progress → scored → reviewed ‖ abandoned
"""

import uuid
from datetime import date

from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models.core import Profile
from tests.helpers import client, grant, h, login

REVIEWER = "09143700037"  # scientific_reviewer (psych.manage + psych.review)
USER_A = "09143700040"
USER_B = "09143700041"


def _mk_test(client, token, code, *, age_min=None, age_max=None):
    body = {
        "code": code,
        "title": "آزمون اضطراب بک-۲ (نمونه)",
        "purpose": "سنجش شدت نشانه‌های اضطراب",
        "target_population": "بزرگسالان ۱۸ تا ۶۰ سال",
        "consent_kind": "psych_test",
        "scientific_doc": "Beck, 1988 — manual",
    }
    if age_min is not None:
        body["age_min"] = age_min
    if age_max is not None:
        body["age_max"] = age_max
    r = client.post("/api/v1/psych-tests", json=body, headers=h(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _mk_version_with_content(client, token, test_id):
    r = client.post(
        f"/api/v1/psych-tests/{test_id}/versions",
        json={"scale_label": "لیکرت چهاردرجه‌ای"},
        headers=h(token),
    )
    assert r.status_code == 201, r.text
    v = r.json()["data"]
    questions = [
        {
            "text": "در دو هفته گذشته چقدر نگران بوده‌اید؟",
            "options": [
                {"label": "هیچ", "score": 0},
                {"label": "کم", "score": 1},
                {"label": "متوسط", "score": 2},
                {"label": "زیاد", "score": 3},
            ],
            "position": 1,
        },
        {
            "text": "در دو هفته گذشته چقدر بی‌قرار بوده‌اید؟",
            "options": [
                {"label": "هیچ", "score": 0},
                {"label": "کم", "score": 1},
                {"label": "متوسط", "score": 2},
                {"label": "زیاد", "score": 3},
            ],
            "position": 2,
        },
    ]
    qids = []
    for q in questions:
        r = client.post(
            f"/api/v1/psych-test-versions/{v['id']}/questions", json=q, headers=h(token)
        )
        assert r.status_code == 201, r.text
        qids.append(r.json()["data"]["id"])
    rules = [
        {
            "min_score": 0,
            "max_score": 1,
            "title": "اضطراب کم",
            "guidance": "وضعیت مطلوب؛ پایش دوره‌ای کافی است.",
        },
        {
            "min_score": 2,
            "max_score": 4,
            "title": "اضطراب متوسط",
            "guidance": "مشاوره تکمیلی توصیه می‌شود.",
        },
        {
            "min_score": 5,
            "max_score": 6,
            "title": "اضطراب شدید",
            "guidance": "ارجاع فوری به متخصص الزامی است.",
        },
    ]
    rule_ids = []
    for rule in rules:
        r = client.post(
            f"/api/v1/psych-test-versions/{v['id']}/interpretation-rules",
            json=rule,
            headers=h(token),
        )
        assert r.status_code == 201, r.text
        rule_ids.append(r.json()["data"]["id"])
    return v, qids, rule_ids


def _setup_published_test(client, reviewer, code, **kw):
    t = _mk_test(client, reviewer, code, **kw)
    v, qids, rule_ids = _mk_version_with_content(client, reviewer, t["id"])
    r = client.post(f"/api/v1/psych-test-versions/{v['id']}/approve", headers=h(reviewer))
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/psych-test-versions/{v['id']}/publish", headers=h(reviewer))
    assert r.status_code == 200, r.text
    return t, v, qids, rule_ids


def test_publish_requires_scientific_approval():
    reviewer, _ = grant(REVIEWER, "scientific_reviewer")
    t = _mk_test(client, reviewer, f"gate-{uuid.uuid4().hex[:8]}")
    v, qids, rule_ids = _mk_version_with_content(client, reviewer, t["id"])
    r = client.post(f"/api/v1/psych-test-versions/{v['id']}/publish", headers=h(reviewer))
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "SCIENTIFIC_APPROVAL_REQUIRED"

    # approval without interpretation rules is rejected (تفسیر مصوب لازم است)
    t2 = _mk_test(client, reviewer, f"norule-{uuid.uuid4().hex[:8]}")
    r = client.post(
        f"/api/v1/psych-tests/{t2['id']}/versions",
        json={"scale_label": "بله/خیر"},
        headers=h(reviewer),
    )
    v2 = r.json()["data"]
    r = client.post(
        f"/api/v1/psych-test-versions/{v2['id']}/questions",
        json={
            "text": "امشب خواب خوبی دارید؟",
            "options": [{"label": "بله", "score": 0}, {"label": "خیر", "score": 1}],
        },
        headers=h(reviewer),
    )
    assert r.status_code == 201
    r = client.post(f"/api/v1/psych-test-versions/{v2['id']}/approve", headers=h(reviewer))
    assert r.status_code == 422
    assert r.json()["errors"][0]["code"] == "NO_INTERPRETATION_RULES"

    # a plain user without psych.manage cannot create tests
    token_a, _ = login(USER_A)
    r = client.post(
        "/api/v1/psych-tests",
        json={"code": f"nope-{uuid.uuid4().hex[:6]}", "title": "تست غیرمجاز"},
        headers=h(token_a),
    )
    assert r.status_code == 403


def _run_scored_attempt(reviewer, code):
    """Publish a test, run USER_A through the full flow, return ids."""
    t, v, qids, rule_ids = _setup_published_test(client, reviewer, code)
    token_a, user_a = login(USER_A)
    # catalog shows published tests
    r = client.get("/api/v1/psych-tests", headers=h(token_a))
    assert r.status_code == 200
    assert any(row["id"] == t["id"] for row in r.json()["data"])

    r = client.post(f"/api/v1/psych-tests/{t['id']}/attempts", headers=h(token_a))
    assert r.status_code == 201, r.text
    attempt_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "started"

    # second start while active → 409
    r = client.post(f"/api/v1/psych-tests/{t['id']}/attempts", headers=h(token_a))
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "ATTEMPT_IN_PROGRESS"

    # questions before consent → 403 (رضایت پیش از اجرا)
    r = client.get(f"/api/v1/psych-attempts/{attempt_id}/questions", headers=h(token_a))
    assert r.status_code == 403
    assert r.json()["errors"][0]["code"] == "CONSENT_REQUIRED"
    r = client.post(
        f"/api/v1/psych-attempts/{attempt_id}/answers",
        json={"answers": [{"question_id": qids[0], "option_index": 0}]},
        headers=h(token_a),
    )
    assert r.status_code == 409

    r = client.post("/api/v1/consents", json={"kind": "psych_test"}, headers=h(token_a))
    assert r.status_code in (201, 409)  # 409 if the active consent already exists
    r = client.post(f"/api/v1/psych-attempts/{attempt_id}/consent", headers=h(token_a))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "consented"

    # questions visible now; option scores must be hidden
    r = client.get(f"/api/v1/psych-attempts/{attempt_id}/questions", headers=h(token_a))
    assert r.status_code == 200
    for q in r.json()["data"]["questions"]:
        for opt in q["options"]:
            assert "score" not in opt

    # invalid option index → 422
    r = client.post(
        f"/api/v1/psych-attempts/{attempt_id}/answers",
        json={"answers": [{"question_id": qids[0], "option_index": 9}]},
        headers=h(token_a),
    )
    assert r.status_code == 422

    # questions added to a non-draft version are rejected (نسخه ثابت)
    r = client.post(
        f"/api/v1/psych-test-versions/{v['id']}/questions",
        json={
            "text": "سؤال پس از انتشار؟",
            "options": [{"label": "الف", "score": 0}, {"label": "ب", "score": 1}],
        },
        headers=h(reviewer),
    )
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "VERSION_IMMUTABLE"

    answers = [
        {"question_id": qids[0], "option_index": 3},
        {"question_id": qids[1], "option_index": 2},
    ]
    r = client.post(
        f"/api/v1/psych-attempts/{attempt_id}/answers",
        json={"answers": answers},
        headers=h(token_a),
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "in_progress"

    r = client.post(f"/api/v1/psych-attempts/{attempt_id}/submit", headers=h(token_a))
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["status"] == "scored"
    assert result["raw_score"] == 5  # 3 + 2
    assert result["interpretation_title"] == "اضطراب شدید"
    assert result["rule_id"] == rule_ids[2]

    # double submit rejected
    r = client.post(f"/api/v1/psych-attempts/{attempt_id}/submit", headers=h(token_a))
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "ATTEMPT_ALREADY_SCORED"

    # my results: traceable interpretation (قابل ردیابی به قاعده مصوب)
    r = client.get("/api/v1/me/psych-results", headers=h(token_a))
    assert r.status_code == 200
    mine = [x for x in r.json()["data"] if x["id"] == attempt_id]
    assert len(mine) == 1
    assert mine[0]["rule_id"] == rule_ids[2]
    assert mine[0]["interpretation_text"] == "ارجاع فوری به متخصص الزامی است."
    return t, attempt_id, user_a, token_a


def test_full_flow_consent_scoring_traceability():
    reviewer, _ = grant(REVIEWER, "scientific_reviewer")
    _run_scored_attempt(reviewer, f"bck-{uuid.uuid4().hex[:8]}")


def test_result_privacy_reviewer_flow():
    reviewer, reviewer_id = grant(REVIEWER, "scientific_reviewer")
    t, attempt_id, user_a, token_a = _run_scored_attempt(
        reviewer, f"prv-{uuid.uuid4().hex[:8]}"
    )

    token_b, user_b = login(USER_B)
    # B cannot read A's attempt (نتیجه فرد دیگر دیده نشود)
    assert (
        client.get(f"/api/v1/psych-attempts/{attempt_id}/questions", headers=h(token_b)).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/psych-attempts/{attempt_id}/submit", headers=h(token_b)).status_code
        == 404
    )
    r = client.get("/api/v1/me/psych-results", headers=h(token_b))
    assert r.status_code == 200
    assert all(x["id"] != attempt_id for x in r.json()["data"])

    # every sensitive read is logged in audit.access_events
    with SessionLocal() as db:
        n = db.execute(
            text(
                "SELECT count(*) FROM audit.access_events "
                "WHERE action = 'psych.result.read' AND subject_user_id = :s"
            ),
            {"s": user_a},
        ).scalar_one()
    assert n >= 2  # owner: submit + me/results

    # reviewer queue + review transition scored → reviewed
    r = client.get("/api/v1/psych-attempts?status=scored", headers=h(reviewer))
    assert r.status_code == 200
    assert any(x["id"] == attempt_id for x in r.json()["data"])
    r = client.post(
        f"/api/v1/psych-attempts/{attempt_id}/review",
        json={"note": "تفسیر مطابق مصوبه نسخه ۱ بررسی شد."},
        headers=h(reviewer),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "reviewed"
    assert r.json()["data"]["review_note"] == "تفسیر مطابق مصوبه نسخه ۱ بررسی شد."

    # plain users cannot access the reviewer queue
    assert client.get("/api/v1/psych-attempts", headers=h(token_b)).status_code == 403
    # and cannot review
    r = client.post(f"/api/v1/psych-attempts/{attempt_id}/review", json={}, headers=h(token_b))
    assert r.status_code in (403, 404)


def test_age_restriction_and_abandon():
    reviewer, _ = grant(REVIEWER, "scientific_reviewer")
    t, v, qids, rule_ids = _setup_published_test(
        client, reviewer, f"age-{uuid.uuid4().hex[:8]}", age_min=40, age_max=60
    )
    token_a, user_a = login(USER_A)
    with SessionLocal() as db:
        profile = db.execute(select(Profile).where(Profile.user_id == user_a)).scalar_one_or_none()
        if profile is None:
            profile = Profile(user_id=user_a)
            db.add(profile)
        profile.birth_date = date(2000, 1, 1)
        db.commit()

    # ۲۶ ساله خارج از بازه ۴۰ تا ۶۰ → ممنوع (محدودیت سنی)
    r = client.post(f"/api/v1/psych-tests/{t['id']}/attempts", headers=h(token_a))
    assert r.status_code == 403
    assert r.json()["errors"][0]["code"] == "AGE_RESTRICTION"

    with SessionLocal() as db:
        profile = db.execute(select(Profile).where(Profile.user_id == user_a)).scalar_one()
        profile.birth_date = date(1975, 5, 5)
        db.commit()

    r = client.post(f"/api/v1/psych-tests/{t['id']}/attempts", headers=h(token_a))
    assert r.status_code == 201
    attempt_id = r.json()["data"]["id"]
    r = client.post(f"/api/v1/psych-attempts/{attempt_id}/abandon", headers=h(token_a))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "abandoned"
    # an abandoned attempt does not block a fresh start
    r = client.post(f"/api/v1/psych-tests/{t['id']}/attempts", headers=h(token_a))
    assert r.status_code == 201
