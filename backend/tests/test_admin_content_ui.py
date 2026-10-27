"""Admin UI backend support endpoints (release 4).

Covers the management reads that back the new admin pages:
- GET /psych-tests/manage — all tests regardless of status + versions (psych.manage)
- GET /psych-test-versions/{id} — questions (with option scores) + rules (psych.manage)
- GET /courses/{id}/detail — modules/lessons/exams of any course, draft included
  (contents.manage)
Plain users are denied on every one of them.
"""

import uuid

from tests.helpers import client, grant, h, login

REVIEWER = "09143800001"
CM = "09143800002"
PLAIN = "09143800003"


def _mk_test_with_version(token: str, code: str) -> tuple[dict, dict]:
    r = client.post(
        "/api/v1/psych-tests",
        json={
            "code": code,
            "title": "آزمون افسردگي بک-۲ (ادمین)",
            "purpose": "سنجش نشانه‌های افسردگی",
            "consent_kind": "psych_test",
        },
        headers=h(token),
    )
    assert r.status_code == 201, r.text
    t = r.json()["data"]
    r = client.post(
        f"/api/v1/psych-tests/{t['id']}/versions",
        json={"scale_label": "لیکرت چهاردرجه‌ای"},
        headers=h(token),
    )
    assert r.status_code == 201, r.text
    return t, r.json()["data"]


def test_psych_manage_listing_and_version_detail():
    reviewer, _ = grant(REVIEWER, "scientific_reviewer")
    code = f"mgmt-{uuid.uuid4().hex[:8]}"
    t, v = _mk_test_with_version(reviewer, code)

    # add one question + one rule so the detail view has content
    r = client.post(
        f"/api/v1/psych-test-versions/{v['id']}/questions",
        json={
            "text": "در دو هفته گذشته چقدر ناامید بوده‌اید؟",
            "options": [
                {"label": "هیچ", "score": 0},
                {"label": "بسیار", "score": 3},
            ],
        },
        headers=h(reviewer),
    )
    assert r.status_code == 201
    r = client.post(
        f"/api/v1/psych-test-versions/{v['id']}/interpretation-rules",
        json={
            "min_score": 0,
            "max_score": 3,
            "title": "افسردگی کم",
            "guidance": "پایش دوره‌ای کافی است.",
        },
        headers=h(reviewer),
    )
    assert r.status_code == 201

    # manage listing shows the draft test with its versions
    r = client.get("/api/v1/psych-tests/manage", headers=h(reviewer))
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["data"] if x["id"] == t["id"])
    assert row["status"] == "draft"  # a draft test the public catalog would hide
    assert any(v["id"] == v["id"] for v in row["versions"])
    assert row["versions"][0]["scale_label"] == "لیکرت چهاردرجه‌ای"

    # version detail includes option scores (admin view) and rules
    r = client.get(f"/api/v1/psych-test-versions/{v['id']}", headers=h(reviewer))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert len(d["questions"]) == 1
    assert {o["score"] for o in d["questions"][0]["options"]} == {0, 3}
    assert len(d["rules"]) == 1
    assert d["rules"][0]["title"] == "افسردگی کم"

    # plain users are denied both reads
    plain, _ = login(PLAIN)
    assert client.get("/api/v1/psych-tests/manage", headers=h(plain)).status_code == 403
    assert (
        client.get(f"/api/v1/psych-test-versions/{v['id']}", headers=h(plain)).status_code == 403
    )


def test_course_detail_admin_editor():
    cm, _ = grant(CM, "content_manager")
    slug = f"ui-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/v1/courses",
        json={"title": "دوره مهارت‌های ارتباطی (ادمین)", "slug": slug, "is_free": True},
        headers=h(cm),
    )
    assert r.status_code == 201, r.text
    course = r.json()["data"]

    r = client.post(
        f"/api/v1/courses/{course['id']}/modules",
        json={"title": "مقدمه", "position": 1},
        headers=h(cm),
    )
    assert r.status_code == 201
    module = r.json()["data"]
    r = client.post(
        f"/api/v1/modules/{module['id']}/lessons",
        json={"title": "درس آشنایی", "lesson_type": "video", "duration_seconds": 600},
        headers=h(cm),
    )
    assert r.status_code == 201
    r = client.post(
        f"/api/v1/courses/{course['id']}/exams",
        json={"title": "آزمون پایانی"},
        headers=h(cm),
    )
    assert r.status_code == 201

    # detail of a DRAFT course works (public detail would 404)
    r = client.get(f"/api/v1/courses/{course['id']}/detail", headers=h(cm))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "draft"
    assert len(d["modules"]) == 1
    assert d["modules"][0]["lessons"][0]["title"] == "درس آشنایی"
    assert len(d["exams"]) == 1
    assert d["exams"][0]["question_count"] == 0

    # plain users denied
    plain, _ = login(PLAIN)
    assert (
        client.get(f"/api/v1/courses/{course['id']}/detail", headers=h(plain)).status_code == 403
    )

    # unknown course → 404
    r = client.get(f"/api/v1/courses/{uuid.uuid4()}/detail", headers=h(cm))
    assert r.status_code == 404
