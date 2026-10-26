"""B20 — Refunds: state machine, over-refund prevention, wallet payout, RBAC."""

import uuid

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h
from tests.test_b18 import _make_pending_appointment_and_order

PHONE = iter(range(9142030000, 9142039999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _paid_order(hok) -> dict:
    """Book + pay via gateway; returns order dict with status=paid."""
    _, order = _make_pending_appointment_and_order(hok)
    start = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    )
    ref = start.json()["data"]["gateway_ref"]
    cb = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": ref, "result": "success"},
        headers=hok,
    )
    assert cb.status_code == 200, cb.text
    return order


def _refund_body(order_id: str, amount: int, reason: str = "انصراف از خدمت") -> dict:
    return {"order_id": order_id, "amount": amount, "reason": reason}


def test_full_refund_lifecycle_to_wallet():
    user, uid = grant(_phone(), "system_admin")
    hok = h(user)
    fin, _ = grant(_phone(), "finance")
    hfin = h(fin)

    order = _paid_order(hok)
    assert order["amount"] == 4500000

    req = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 4500000), headers=hok
    )
    assert req.status_code == 201, req.text
    assert req.json()["data"]["status"] == "submitted"
    rid = req.json()["data"]["id"]

    # duplicate active request rejected
    dup = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 4500000), headers=hok
    )
    assert dup.status_code == 409

    # user without refunds.manage cannot approve (RBAC + audit)
    plain, _ = grant(_phone(), "consultant")
    denied = client.post(f"/api/v1/refund-requests/{rid}/approve", headers=h(plain))
    assert denied.status_code == 403

    # invalid transition: approve directly from submitted
    skip = client.post(
        f"/api/v1/refund-requests/{rid}/approve", json={"note": None}, headers=hfin
    )
    assert skip.status_code == 409

    rv = client.post(f"/api/v1/refund-requests/{rid}/review", headers=hfin)
    assert rv.json()["data"]["status"] == "reviewing"
    ap = client.post(
        f"/api/v1/refund-requests/{rid}/approve",
        json={"note": "تأیید مدیر مالی"},
        headers=hfin,
    )
    assert ap.json()["data"]["status"] == "approved"

    ex = client.post(f"/api/v1/refund-requests/{rid}/execute", headers=hfin)
    assert ex.status_code == 200, ex.text
    assert ex.json()["data"]["amount"] == 4500000
    assert ex.json()["data"]["request_status"] == "executed"

    # money in wallet
    wallet = client.get("/api/v1/wallet", headers=hok).json()["data"]
    assert wallet["balance"] == 4500000
    entries = client.get("/api/v1/wallet/entries", headers=hok).json()["data"]
    assert entries[0]["entry_type"] == "refund"
    assert entries[0]["direction"] == "credit"

    # order fully refunded
    o = client.get(f"/api/v1/orders/{order['id']}", headers=hok).json()["data"]
    assert o["status"] == "refunded"

    # double execution rejected
    ex2 = client.post(f"/api/v1/refund-requests/{rid}/execute", headers=hfin)
    assert ex2.status_code == 409
    assert ex2.json()["errors"][0]["code"] == "REFUND_ALREADY_EXECUTED"


def test_partial_then_remaining_refund():
    user, _ = grant(_phone(), "system_admin")
    hok = h(user)
    fin, _ = grant(_phone(), "finance")
    hfin = h(fin)
    order = _paid_order(hok)

    r1 = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 2000000), headers=hok
    )
    rid1 = r1.json()["data"]["id"]
    for step in ("review", "approve", "execute"):
        client.post(f"/api/v1/refund-requests/{rid1}/{step}", headers=hfin)

    # over-refund rejected (remaining 2.5M)
    over = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 3000000), headers=hok
    )
    assert over.status_code == 409
    assert over.json()["errors"][0]["code"] == "REFUND_EXCEEDS_REMAINING"

    # remaining partial refund succeeds; order becomes refunded
    r2 = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 2500000), headers=hok
    )
    rid2 = r2.json()["data"]["id"]
    for step in ("review", "approve", "execute"):
        client.post(f"/api/v1/refund-requests/{rid2}/{step}", headers=hfin)
    o = client.get(f"/api/v1/orders/{order['id']}", headers=hok).json()["data"]
    assert o["status"] == "refunded"

    # refunds exceed prevention: third request impossible on refunded order
    r3 = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 1000000), headers=hok
    )
    assert r3.status_code == 409
    assert r3.json()["errors"][0]["code"] == "REFUND_ORDER_NOT_PAID"


def test_refund_on_unpaid_order_rejected():
    user, _ = grant(_phone(), "system_admin")
    hok = h(user)
    _, order = _make_pending_appointment_and_order(hok)
    r = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 1000000), headers=hok
    )
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "REFUND_ORDER_NOT_PAID"


def test_user_lists_own_requests_finance_lists_all():
    u1, _ = grant(_phone(), "system_admin")
    fin, _ = grant(_phone(), "finance")
    hok = h(u1)
    order = _paid_order(hok)
    req = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 1500000), headers=hok
    ).json()["data"]

    own = client.get("/api/v1/refund-requests", headers=hok).json()["data"]
    assert len(own) == 1
    assert own[0]["id"] == req["id"]

    all_rows = client.get("/api/v1/refund-requests", headers=h(fin)).json()["data"]
    assert any(x["id"] == req["id"] for x in all_rows)


def test_reject_flow():
    user, _ = grant(_phone(), "system_admin")
    hok = h(user)
    fin, _ = grant(_phone(), "finance")
    hfin = h(fin)
    order = _paid_order(hok)
    req = client.post(
        "/api/v1/refund-requests",
        json=_refund_body(order["id"], 500000, reason="درخواست بی‌مبنا"),
        headers=hok,
    ).json()["data"]
    rj = client.post(
        f"/api/v1/refund-requests/{req['id']}/reject",
        json={"note": "مدرک کافی نیست"},
        headers=hfin,
    )
    assert rj.status_code == 200, rj.text
    assert rj.json()["data"]["status"] == "rejected"

    # rejected request cannot be executed
    ex = client.post(f"/api/v1/refund-requests/{req['id']}/execute", headers=hfin)
    assert ex.status_code == 409


def test_wallet_balance_matches_entries_after_refund():
    user, uid = grant(_phone(), "system_admin")
    hok = h(user)
    fin, _ = grant(_phone(), "finance")
    hfin = h(fin)
    order = _paid_order(hok)
    req = client.post(
        "/api/v1/refund-requests", json=_refund_body(order["id"], 4500000), headers=hok
    ).json()["data"]
    for step in ("review", "approve", "execute"):
        client.post(f"/api/v1/refund-requests/{req['id']}/{step}", headers=hfin)
    with engine.begin() as conn:
        computed = conn.execute(
            text(
                "SELECT COALESCE(SUM(CASE WHEN e.direction='credit' THEN e.amount "
                "ELSE -e.amount END), 0)::int FROM finance.wallet_entries e "
                "JOIN finance.wallets w ON w.id = e.wallet_id WHERE w.user_id = :u"
            ),
            {"u": uuid.UUID(uid)},
        ).scalar_one()
        stored = conn.execute(
            text(
                "SELECT balance_after FROM finance.wallet_entries e "
                "JOIN finance.wallets w ON w.id = e.wallet_id WHERE w.user_id = :u "
                "ORDER BY e.created_at DESC LIMIT 1"
            ),
            {"u": uuid.UUID(uid)},
        ).scalar_one()
    assert int(stored) == computed
