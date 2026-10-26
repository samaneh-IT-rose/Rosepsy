"""B18 — Wallet: ledger consistency, topup via gateway, pay from balance, no double-spend."""

import uuid

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h

PHONE = iter(range(9142010000, 9142019999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _balance(user_id: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount "
                "ELSE -amount END), 0)::int FROM finance.wallet_entries "
                "WHERE wallet_id = (SELECT id FROM finance.wallets WHERE user_id = :u)"
            ),
            {"u": uuid.UUID(user_id)},
        ).scalar_one()


def test_wallet_auto_created_with_zero_balance():
    token, uid = grant(_phone(), "system_admin")
    r = client.get("/api/v1/wallet", headers=h(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["user_id"] == uid
    assert data["balance"] == 0
    assert data["currency"] == "IRR"


def test_topup_via_gateway_credits_wallet():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    order = client.post(
        "/api/v1/wallet-topups",
        json={"amount": 500000},
        headers={**hok, "Idempotency-Key": "topup-1"},
    )
    assert order.status_code == 201, order.text
    odata = order.json()["data"]
    assert odata["order_type"] == "wallet_topup"

    # idempotent replay
    replay = client.post(
        "/api/v1/wallet-topups",
        json={"amount": 500000},
        headers={**hok, "Idempotency-Key": "topup-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["id"] == odata["id"]
    assert replay.json()["meta"]["idempotent_replay"] is True

    start = client.post(
        "/api/v1/payments/start", json={"order_id": odata["id"]}, headers=hok
    )
    assert start.status_code == 200, start.text
    ref = start.json()["data"]["gateway_ref"]

    cb = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": ref, "result": "success"},
        headers=hok,
    )
    assert cb.status_code == 200, cb.text
    assert cb.json()["data"]["invoice_id"] is None  # topups have no invoice

    wallet = client.get("/api/v1/wallet", headers=hok).json()["data"]
    assert wallet["balance"] == 500000

    entries = client.get("/api/v1/wallet/entries", headers=hok).json()
    assert entries["meta"]["balance"] == 500000
    top = entries["data"][0]
    assert top["direction"] == "credit"
    assert top["entry_type"] == "topup"
    assert top["amount"] == 500000
    assert top["balance_after"] == 500000


def test_repeated_callback_is_noop_no_double_credit():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    order = client.post(
        "/api/v1/wallet-topups",
        json={"amount": 300000},
        headers={**hok, "Idempotency-Key": "topup-2"},
    ).json()["data"]
    ref = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]["gateway_ref"]
    cb1 = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": ref, "result": "success"},
        headers=hok,
    )
    assert cb1.json()["data"]["noop"] is False
    cb2 = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": ref, "result": "success"},
        headers=hok,
    )
    assert cb2.json()["data"]["noop"] is True
    assert client.get("/api/v1/wallet", headers=hok).json()["data"]["balance"] == 300000


def test_finance_credit_is_idempotent_and_user_only_for_self():
    ftoken, _ = grant(_phone(), "finance")
    user_token, user_id = grant(_phone(), "consultant")
    hfin = h(ftoken)

    body = {"user_id": user_id, "amount": 120000, "note": "هدیه باشگاه"}
    r1 = client.post(
        "/api/v1/wallet/credits",
        json=body,
        headers={**hfin, "Idempotency-Key": "adj-1"},
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        "/api/v1/wallet/credits",
        json=body,
        headers={**hfin, "Idempotency-Key": "adj-1"},
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == r1.json()["data"]["id"]
    assert _balance(user_id) == 120000

    # a user without wallet.manage cannot credit
    denied = client.post(
        "/api/v1/wallet/credits",
        json={"user_id": user_id, "amount": 1},
        headers=h(user_token),
    )
    assert denied.status_code == 403

    # viewing someone else's wallet without permission is denied
    denied2 = client.get(f"/api/v1/wallets/{user_id}", headers=h(user_token))
    assert denied2.status_code == 403


def _make_pending_appointment_and_order(
    hok, discount: str | None = None, book_with: dict | None = None, slot_minute: int = 0
):
    """Paid 45min service (4.5M IRR) booked next Monday -> awaiting_payment order.
    `hok` performs the admin setup; `book_with` (optional) books as another user.
    slot_minute: offset from 09:00 on the 45-minute slot grid (0, 45, 90, ...)."""
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر کیف"}, headers=hok
    ).json()["data"]["id"]
    cred = client.post(
        f"/api/v1/consultants/{cid}/credentials",
        json={
            "kind": "license",
            "title": "پروانه",
            "license_number": f"LIC-{uuid.uuid4().hex[:8]}",
        },
        headers=hok,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/verification-reviews",
        json={"credential_id": cred, "decision": "approved"},
        headers=hok,
    )
    sid = client.post(
        "/api/v1/services", json={"name": "خدمت کیف پول", "duration_minutes": 45},
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
    from datetime import UTC, datetime, time, timedelta
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Tehran")
    today = datetime.now(UTC).date()
    days_ahead = (0 - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead else 7
    start_at = datetime.combine(
        today + timedelta(days=days_ahead), time(9, slot_minute), tzinfo=TZ
    )
    hbook = book_with or hok
    hold = client.post(
        "/api/v1/booking-holds",
        json={
            "consultant_id": cid,
            "service_id": sid,
            "start_at": start_at.astimezone(UTC).isoformat(),
        },
        headers=hbook,
    ).json()["data"]
    appt = client.post(
        "/api/v1/appointments", json={"hold_id": hold["id"]}, headers=hbook
    ).json()["data"]
    body = {"appointment_id": appt["id"]}
    if discount:
        body["discount_code"] = discount
    order = client.post(
        "/api/v1/orders",
        json=body,
        headers={**hbook, "Idempotency-Key": f"ord-{uuid.uuid4().hex[:10]}"},
    )
    assert order.status_code == 201, order.text
    return appt, order.json()["data"]


def test_pay_from_wallet_full_flow():
    token, uid = grant(_phone(), "system_admin")
    hok = h(token)
    # topup 5M
    order = client.post(
        "/api/v1/wallet-topups",
        json={"amount": 5000000},
        headers={**hok, "Idempotency-Key": "topup-flow-1"},
    ).json()["data"]
    ref = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]["gateway_ref"]
    client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": ref, "result": "success"},
        headers=hok,
    )

    appt, ord_data = _make_pending_appointment_and_order(hok)
    pay = client.post(
        "/api/v1/wallet/pay", json={"order_id": ord_data["id"]}, headers=hok
    )
    assert pay.status_code == 200, pay.text
    pdata = pay.json()["data"]
    assert pdata["order_status"] == "paid"
    assert pdata["invoice_id"] is not None
    assert pdata["balance_after"] == 500000  # 5M - 4.5M

    appt_now = client.get(f"/api/v1/appointments/{appt['id']}", headers=hok).json()["data"]
    assert appt_now["status"] == "confirmed"
    assert _balance(uid) == 500000

    # double pay rejected
    again = client.post(
        "/api/v1/wallet/pay", json={"order_id": ord_data["id"]}, headers=hok
    )
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "INVALID_ORDER_STATUS"
    assert _balance(uid) == 500000  # unchanged


def test_pay_from_wallet_insufficient_funds():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    _, ord_data = _make_pending_appointment_and_order(hok)
    pay = client.post(
        "/api/v1/wallet/pay", json={"order_id": ord_data["id"]}, headers=hok
    )
    assert pay.status_code == 409
    assert pay.json()["errors"][0]["code"] == "WALLET_INSUFFICIENT_FUNDS"
    # order stays awaiting_payment
    o = client.get(f"/api/v1/orders/{ord_data['id']}", headers=hok).json()["data"]
    assert o["status"] == "awaiting_payment"


def test_cannot_pay_topup_order_with_wallet():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    order = client.post(
        "/api/v1/wallet-topups",
        json={"amount": 100000},
        headers={**hok, "Idempotency-Key": "topup-self-1"},
    ).json()["data"]
    r = client.post("/api/v1/wallet/pay", json={"order_id": order["id"]}, headers=hok)
    assert r.status_code == 409


def test_other_users_order_is_not_visible_or_payable():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    _, ord_data = _make_pending_appointment_and_order(hok)
    other, _ = grant(_phone(), "consultant")
    r = client.post(
        "/api/v1/wallet/pay", json={"order_id": ord_data["id"]}, headers=h(other)
    )
    assert r.status_code == 404
