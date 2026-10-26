"""B23 — Surveys & support tickets: no clinical exposure, staff workflow."""


from tests.helpers import client, grant, h, login

PHONE = iter(range(9142060000, 9142069999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def test_survey_submission_and_duplicate_guard():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    r = client.post(
        "/api/v1/survey-responses",
        json={"score": 9, "comment": "تجربه خوبی بود"},
        headers=hok,
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["score"] == 9

    # out-of-range score
    bad = client.post(
        "/api/v1/survey-responses", json={"score": 11}, headers=hok
    )
    assert bad.status_code == 422


def test_ticket_lifecycle_with_staff_workflow():
    user, _ = login(_phone())  # plain user, no tickets.manage
    hok = h(user)
    staff, _ = grant(_phone(), "reception")  # reception has tickets.manage
    hstaff = h(staff)

    t = client.post(
        "/api/v1/support-tickets",
        json={
            "subject": "مشکل در پرداخت",
            "body": "پرداخت من دو بار کسر شده است لطفا بررسی کنید.",
            "priority": "high",
        },
        headers=hok,
    )
    assert t.status_code == 201, t.text
    tid = t.json()["data"]["id"]
    assert t.json()["data"]["status"] == "open"

    # user lists own tickets
    own = client.get("/api/v1/support-tickets", headers=hok).json()["data"]
    assert any(x["id"] == tid for x in own)

    # staff sees all tickets
    all_rows = client.get("/api/v1/support-tickets", headers=hstaff).json()["data"]
    assert any(x["id"] == tid for x in all_rows)

    # stranger cannot see the ticket
    stranger, _ = grant(_phone(), "consultant")
    hidden = client.get(f"/api/v1/support-tickets/{tid}", headers=h(stranger))
    assert hidden.status_code == 404

    # staff reply moves ticket to in_progress
    msg = client.post(
        f"/api/v1/support-tickets/{tid}/messages",
        json={"body": "در حال بررسی هستیم."},
        headers=hstaff,
    )
    assert msg.status_code == 201, msg.text
    assert msg.json()["data"]["is_staff"] is True
    assert msg.json()["data"]["ticket_status"] == "in_progress"

    # user replies too
    umsg = client.post(
        f"/api/v1/support-tickets/{tid}/messages",
        json={"body": "ممنون، منتظر می‌مانم."},
        headers=hok,
    )
    assert umsg.status_code == 201
    assert umsg.json()["data"]["is_staff"] is False

    # stranger cannot reply
    sdenied = client.post(
        f"/api/v1/support-tickets/{tid}/messages",
        json={"body": "سلام"},
        headers=h(stranger),
    )
    assert sdenied.status_code == 404

    detail = client.get(f"/api/v1/support-tickets/{tid}", headers=hok).json()["data"]
    assert len(detail["messages"]) == 2

    # resolve
    res = client.post(
        f"/api/v1/support-tickets/{tid}/status",
        json={"status": "resolved"},
        headers=hstaff,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["resolved_at"] is not None

    # closed ticket rejects new messages
    closed = client.post(
        f"/api/v1/support-tickets/{tid}/messages",
        json={"body": "باز شود"},
        headers=hok,
    )
    assert closed.status_code == 409

    # status transition from resolved is rejected
    again = client.post(
        f"/api/v1/support-tickets/{tid}/status",
        json={"status": "closed"},
        headers=hstaff,
    )
    assert again.status_code == 409


def test_ticket_without_permission_cannot_change_status():
    user, _ = login(_phone())  # plain user
    hok = h(user)
    t = client.post(
        "/api/v1/support-tickets",
        json={"subject": "سوال عمومی", "body": "یک سوال بدون فوریت"},
        headers=hok,
    ).json()["data"]
    # ticket owner without tickets.manage cannot force status change
    denied = client.post(
        f"/api/v1/support-tickets/{t['id']}/status",
        json={"status": "resolved"},
        headers=hok,
    )
    assert denied.status_code == 403
