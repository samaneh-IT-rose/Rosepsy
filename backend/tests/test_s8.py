from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from tests.helpers import client, grant, h, login

PHONE = iter(range(9141180000, 9141189999))
TZ = ZoneInfo("Asia/Tehran")


def _phone() -> str:
    return "0" + str(next(PHONE))


def _next_monday() -> datetime:
    today = datetime.now(UTC).date()
    days_ahead = (0 - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead else 7
    return datetime.combine(today + timedelta(days=days_ahead), time(9, 0), tzinfo=TZ)


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _setup_paid():
    """admin + eligible consultant + 45min paid service (4.5M IRR) + Monday rule."""
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر پرداخت"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={"kind": "license", "title": "پروانه", "license_number": "LIC-B10"},
        headers=hok,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "approved"},
        headers=hok,
    )
    sid = client.post(
        "/api/v1/services", json={"name": "خدمت پرداختی", "duration_minutes": 45},
        headers=hok,
    ).json()["data"]["id"]
    tid = client.post(
        "/api/v1/tariffs", json={"service_id": sid}, headers=hok
    ).json()["data"]["id"]
    client.post(
        f"/api/v1/tariffs/{tid}/versions",
        json={"amount": 4500000, "valid_from": "2024-01-01T00:00:00Z"},
        headers=hok,
    )
    client.put(
        f"/api/v1/consultants/{cid}/availability-rules",
        json={"rules": [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]},
        headers=hok,
    )
    return token, hok, cid, sid


def _pending_appointment(hok, cid, sid) -> dict:
    hold = client.post(
        "/api/v1/booking-holds",
        json={"consultant_id": cid, "service_id": sid, "start_at": _utc(_next_monday())},
        headers=hok,
    ).json()["data"]
    appt = client.post("/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok)
    assert appt.status_code == 201, appt.text
    return appt.json()["data"]


def _mk_order(hok, appt_id: str, key: str):
    return client.post(
        "/api/v1/orders",
        json={"appointment_id": appt_id},
        headers={**hok, "Idempotency-Key": key},
    )


def _start(hok, order_id: str) -> dict:
    r = client.post("/api/v1/payments/start", json={"order_id": order_id}, headers=hok)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _callback(hok, gateway_ref: str, result: str):
    return client.post(
        "/api/v1/payments/callback", json={"gateway_ref": gateway_ref, "result": result},
        headers=hok,
    )


def test_order_requires_idempotency_key():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    r = client.post("/api/v1/orders", json={"appointment_id": appt["id"]}, headers=hok)
    assert r.status_code == 400
    assert r.json()["errors"][0]["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_order_created_with_snapshot_amount():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    r = _mk_order(hok, appt["id"], "key-1")
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["amount"] == 4500000 == appt["price_snapshot"]["amount"]
    assert data["status"] == "awaiting_payment"


def test_order_idempotent_replay_same_order():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    first = _mk_order(hok, appt["id"], "key-2")
    second = _mk_order(hok, appt["id"], "key-2")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["meta"]["idempotent_replay"] is True
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


def test_order_for_foreign_appointment_404():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    other_token, _ = login(_phone())
    r = _mk_order(h(other_token), appt["id"], "key-3")
    assert r.status_code == 404


def test_order_for_non_pending_appointment_409():
    _, hok, cid, sid = _setup_paid()
    sid_free = client.post(
        "/api/v1/services", json={"name": "خدمت رایگان", "duration_minutes": 30},
        headers=hok,
    ).json()["data"]["id"]
    hold = client.post(
        "/api/v1/booking-holds",
        json={
            "consultant_id": cid,
            "service_id": sid_free,
            "start_at": _utc(_next_monday().replace(hour=11)),
        },
        headers=hok,
    ).json()["data"]
    appt = client.post(
        "/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hok
    ).json()["data"]
    assert appt["status"] == "confirmed"
    r = _mk_order(hok, appt["id"], "key-4")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "INVALID_APPOINTMENT_STATUS"


def test_duplicate_active_order_409():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    assert _mk_order(hok, appt["id"], "key-5a").status_code == 201
    r = _mk_order(hok, appt["id"], "key-5b")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "ORDER_EXISTS"


def test_payment_start_initiates_once():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-6").json()["data"]
    data = _start(hok, order["id"])
    assert data["gateway_ref"].startswith("mock-")
    assert "/mock-gateway/pay" in data["redirect_url"]
    again = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    )
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "PAYMENT_IN_PROGRESS"


def test_callback_success_full_flow():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-7").json()["data"]
    start = _start(hok, order["id"])
    cb = _callback(hok, start["gateway_ref"], "success")
    assert cb.status_code == 200, cb.text
    data = cb.json()["data"]
    assert data["order_status"] == "paid"
    assert data["invoice_id"]

    got_appt = client.get(f"/api/v1/appointments/{appt['id']}", headers=hok).json()["data"]
    assert got_appt["status"] == "confirmed"

    inv = client.get(f"/api/v1/invoices/{data['invoice_id']}", headers=hok).json()["data"]
    assert inv["amount"] == 4500000 == order["amount"]
    assert inv["invoice_number"].startswith("INV-")
    assert len(inv["items"]) == 1 and inv["items"][0]["total"] == 4500000


def test_repeated_callback_noop():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-8").json()["data"]
    start = _start(hok, order["id"])
    first = _callback(hok, start["gateway_ref"], "success")
    assert first.json()["data"]["noop"] is False
    second = _callback(hok, start["gateway_ref"], "success")
    assert second.status_code == 200
    assert second.json()["data"]["noop"] is True
    with engine.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM finance.invoices")).scalar_one()
    assert count == 1  # no duplicate invoice


def test_callback_failure_then_new_order():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-9").json()["data"]
    start = _start(hok, order["id"])
    fail = _callback(hok, start["gateway_ref"], "failure")
    assert fail.json()["data"]["order_status"] == "failed"
    order2 = _mk_order(hok, appt["id"], "key-9b")
    assert order2.status_code == 201, order2.text
    start2 = _start(hok, order2.json()["data"]["id"])
    ok = _callback(hok, start2["gateway_ref"], "success")
    assert ok.json()["data"]["order_status"] == "paid"


def test_invoice_visibility_matrix():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-10").json()["data"]
    start = _start(hok, order["id"])
    invoice_id = _callback(hok, start["gateway_ref"], "success").json()["data"]["invoice_id"]

    owner = client.get(f"/api/v1/invoices/{invoice_id}", headers=hok)
    assert owner.status_code == 200

    fin_token, _ = grant(_phone(), "finance")
    fin = client.get(f"/api/v1/invoices/{invoice_id}", headers=h(fin_token))
    assert fin.status_code == 200

    stranger_token, _ = login(_phone())
    stranger = client.get(f"/api/v1/invoices/{invoice_id}", headers=h(stranger_token))
    assert stranger.status_code == 404


def test_invoice_pdf_content_type():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-11").json()["data"]
    start = _start(hok, order["id"])
    invoice_id = _callback(hok, start["gateway_ref"], "success").json()["data"]["invoice_id"]
    pdf = client.get(f"/api/v1/invoices/{invoice_id}.pdf", headers=hok)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-1.4")


def test_payment_start_on_paid_order_409():
    _, hok, cid, sid = _setup_paid()
    appt = _pending_appointment(hok, cid, sid)
    order = _mk_order(hok, appt["id"], "key-12").json()["data"]
    start = _start(hok, order["id"])
    _callback(hok, start["gateway_ref"], "success")
    again = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    )
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "INVALID_ORDER_STATUS"


def test_callback_ip_allowlist_blocks(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_CALLBACK_ALLOWLIST", "10.99.99.99")
    resp = _callback(h({}), "mock-nonexistent", "success")
    assert resp.status_code == 403
    assert resp.json()["errors"][0]["code"] == "FORBIDDEN"
