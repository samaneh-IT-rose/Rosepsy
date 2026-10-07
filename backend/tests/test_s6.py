from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from tests.helpers import client, denied_count, grant, h, login

PHONE = iter(range(9141160000, 9141169999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _next_monday() -> date:
    today = datetime.now(UTC).date()
    days_ahead = (0 - today.weekday()) % 7
    return today + timedelta(days=days_ahead if days_ahead else 7)


def _mk_consultant(hok) -> str:
    r = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر تقویم"}, headers=hok
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _mk_service(hok, minutes: int) -> str:
    r = client.post(
        "/api/v1/services",
        json={"name": f"خدمت {minutes} دقیقه", "duration_minutes": minutes},
        headers=hok,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def test_rules_require_permission_and_denial_audited():
    token, uid = login(_phone())
    resp = client.put(
        f"/api/v1/consultants/{UUID(int=50)}/availability-rules",
        json={"rules": []},
        headers=h(token),
    )
    assert resp.status_code == 403
    assert denied_count(uid, "permission:availability.manage") == 1


def test_invalid_window_rejected():
    token, _ = grant(_phone(), "system_admin")
    cid = _mk_consultant(h(token))
    resp = client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": 0, "start_time": "18:00", "end_time": "09:00"}]},
        headers=h(token),
    )
    assert resp.status_code == 422


def test_overlapping_rules_same_weekday_rejected():
    token, _ = grant(_phone(), "system_admin")
    cid = _mk_consultant(h(token))
    resp = client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={
            "rules": [
                {"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
                {"weekday": 0, "start_time": "11:00", "end_time": "14:00"},
            ]
        },
        headers=h(token),
    )
    assert resp.status_code == 409
    assert resp.json()["errors"][0]["code"] == "OVERLAPPING_RULES"


def test_put_replaces_rules_idempotently():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = _mk_consultant(hok)
    first = client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={
            "rules": [
                {"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
                {"weekday": 2, "start_time": "14:00", "end_time": "18:00"},
            ]
        },
        headers=hok,
    )
    assert first.status_code == 200
    second = client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]},
        headers=hok,
    )
    assert second.status_code == 200
    listing = client.get(f"/api/v1/consultants/{cid}/availability-rules", headers=hok)
    data = listing.json()["data"]
    assert len(data) == 1 and data[0]["weekday"] == 0  # replaced, not appended


def test_consultant_manages_own_calendar_not_others():
    admin_token, _ = grant(_phone(), "system_admin")
    own_token, _ = grant(_phone(), "consultant")
    # link own_token's user to a consultant profile via admin
    me = client.get("/api/v1/me", headers=h(own_token)).json()["data"]
    own_cid = client.post(
        "/api/v1/consultants", json={"display_name": "خودم", "user_id": me["id"]},
        headers=h(admin_token),
    ).json()["data"]["id"]
    other_cid = _mk_consultant(h(admin_token))

    own_edit = client.put(
        f"/api/v1/consultants/{own_cid}/availability-rules",
        json={"rules": [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]},
        headers=h(own_token),
    )
    assert own_edit.status_code == 200  # own calendar OK

    other_edit = client.put(
        f"/api/v1/consultants/{other_cid}/availability-rules",
        json={"rules": []},
        headers=h(own_token),
    )
    assert other_edit.status_code == 403  # someone else's calendar denied


def test_slots_for_service_over_range():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = _mk_consultant(hok)
    sid = _mk_service(hok, 45)
    monday = _next_monday()
    put = client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": monday.weekday(), "start_time": "09:00", "end_time": "10:30"}]},
        headers=hok,
    )
    assert put.status_code == 200
    slots = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid, "from": monday.isoformat(), "to": monday.isoformat()},
        headers=hok,
    )
    assert slots.status_code == 200, slots.text
    data = slots.json()["data"]
    assert data["duration_minutes"] == 45
    assert len(data["dates"][monday.isoformat()]) == 2  # 09:00 and 09:45


def test_exception_blocks_and_delete_restores():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = _mk_consultant(hok)
    sid = _mk_service(hok, 60)
    monday = _next_monday()
    client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": monday.weekday(), "start_time": "09:00", "end_time": "12:00"}]},
        headers=hok,
    )
    base = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid, "from": monday.isoformat(), "to": monday.isoformat()},
        headers=hok,
    ).json()["data"]
    assert len(base["dates"][monday.isoformat()]) == 3  # 09,10,11

    # block 10:00-11:00 local == 06:30-07:30 UTC
    exc = client.post(
        f"/api/v1/consultants/{cid}/availability-exceptions",
        json={
            "start_at": f"{monday.isoformat()}T06:30:00Z",
            "end_at": f"{monday.isoformat()}T07:30:00Z",
            "reason": "جلسه داخلی",
        },
        headers=hok,
    )
    assert exc.status_code == 201
    blocked = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid, "from": monday.isoformat(), "to": monday.isoformat()},
        headers=hok,
    ).json()["data"]
    starts = [s["start"][11:16] for s in blocked["dates"][monday.isoformat()]]
    assert "06:30" not in starts and len(starts) == 2

    removed = client.delete(
        f"/api/v1/consultants/{cid}/availability-exceptions/{exc.json()['data']['id']}",
        headers=hok,
    )
    assert removed.status_code == 200
    restored = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid, "from": monday.isoformat(), "to": monday.isoformat()},
        headers=hok,
    ).json()["data"]
    assert len(restored["dates"][monday.isoformat()]) == 3


def test_inactive_service_rejected_for_slots():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = _mk_consultant(hok)
    sid = _mk_service(hok, 45)
    client.patch(f"/api/v1/services/{sid}", json={"is_active": False}, headers=hok)
    resp = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid},
        headers=hok,
    )
    assert resp.status_code == 404
    assert resp.json()["errors"][0]["code"] == "SERVICE_NOT_FOUND"


def test_range_too_long_rejected():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = _mk_consultant(hok)
    sid = _mk_service(hok, 45)
    resp = client.get(
        f"/api/v1/consultants/{cid}/availability",
        params={"service_id": sid, "from": "2025-01-01", "to": "2025-06-01"},
        headers=hok,
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "RANGE_TOO_LONG"


def test_missing_consultant_404():
    token, _ = grant(_phone(), "system_admin")
    resp = client.get(
        f"/api/v1/consultants/{UUID(int=77)}/availability",
        params={"service_id": str(UUID(int=78))},
        headers=h(token),
    )
    assert resp.status_code == 404


def test_exception_invalid_range_rejected():
    token, _ = grant(_phone(), "system_admin")
    cid = _mk_consultant(h(token))
    resp = client.post(
        f"/api/v1/consultants/{cid}/availability-exceptions",
        json={"start_at": "2025-06-20T10:00:00Z", "end_at": "2025-06-20T09:00:00Z"},
        headers=h(token),
    )
    assert resp.status_code == 422
