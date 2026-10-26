"""B22 — Accounting: balanced journals, source idempotency, settlements."""

import uuid
from datetime import UTC, datetime, timedelta

from tests.helpers import client, grant, h

PHONE = iter(range(9142050000, 9142059999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _balanced_lines(amount: int) -> list[dict]:
    return [
        {"account_code": "1001", "debit": amount},
        {"account_code": "4000", "credit": amount},
    ]


def test_journal_must_balance():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    unbalanced = client.post(
        "/api/v1/journal-entries",
        json={
            "description": "سند نامتوازن",
            "lines": [
                {"account_code": "1001", "debit": 1000},
                {"account_code": "4000", "credit": 900},
            ],
        },
        headers=hok,
    )
    assert unbalanced.status_code == 422
    assert unbalanced.json()["errors"][0]["code"] == "JOURNAL_NOT_BALANCED"

    single = client.post(
        "/api/v1/journal-entries",
        json={"lines": [{"account_code": "1001", "debit": 1000}]},
        headers=hok,
    )
    assert single.status_code == 422

    two_side = client.post(
        "/api/v1/journal-entries",
        json={
            "lines": [
                {"account_code": "1001", "debit": 1000, "credit": 500},
                {"account_code": "4000", "credit": 500},
            ]
        },
        headers=hok,
    )
    assert two_side.status_code == 422


def test_journal_post_and_source_idempotency():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    src = uuid.uuid4()
    r1 = client.post(
        "/api/v1/journal-entries",
        json={
            "description": "درآمد خدمات",
            "source_type": "order",
            "source_id": str(src),
            "lines": _balanced_lines(4500000),
        },
        headers=hok,
    )
    assert r1.status_code == 201, r1.text
    d1 = r1.json()["data"]
    assert d1["total_debit"] == 4500000
    assert d1["total_credit"] == 4500000
    assert {ln["account_code"] for ln in d1["lines"]} == {"1001", "4000"}

    # same source -> same entry (idempotent)
    r2 = client.post(
        "/api/v1/journal-entries",
        json={
            "description": "تلاش دوباره",
            "source_type": "order",
            "source_id": str(src),
            "lines": _balanced_lines(4500000),
        },
        headers=hok,
    )
    assert r2.status_code == 201
    assert r2.json()["data"]["id"] == d1["id"]

    # listing shows the entry with balances
    listed = client.get("/api/v1/journal-entries", headers=hok).json()["data"]
    assert any(e["id"] == d1["id"] for e in listed)


def test_order_payment_auto_posts_journal():
    """The full booking+payment flow must produce a traceable journal entry."""
    from tests.test_b18 import _make_pending_appointment_and_order

    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    _, order = _make_pending_appointment_and_order(hok)
    start = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]
    cb = client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )
    assert cb.status_code == 200, cb.text

    entries = client.get("/api/v1/journal-entries", headers=hok).json()["data"]
    match = [e for e in entries if e["source_type"] == "order" and e["source_id"] == order["id"]]
    assert len(match) == 1
    assert match[0]["total_debit"] == match[0]["total_credit"] == 4500000

    # account balances reflect the journal
    accounts = client.get("/api/v1/accounts", headers=hok).json()["data"]
    cash = next(a for a in accounts if a["code"] == "1001")
    revenue = next(a for a in accounts if a["code"] == "4000")
    assert cash["balance"] == 4500000
    assert revenue["balance"] == -4500000  # credit side


def test_settlement_lifecycle():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "دکتر تسویه"}, headers=hok
    ).json()["data"]["id"]
    now = datetime.now(UTC)
    st = client.post(
        "/api/v1/settlements",
        json={
            "consultant_id": cid,
            "period_from": (now - timedelta(days=30)).isoformat(),
            "period_to": now.isoformat(),
            "gross_amount": 10000000,
            "share_percent": 40,
        },
        headers=hok,
    )
    assert st.status_code == 201, st.text
    data = st.json()["data"]
    assert data["net_amount"] == 6000000  # 60% of gross
    assert data["status"] == "draft"

    adv = client.post(f"/api/v1/settlements/{data['id']}/advance", headers=hok)
    assert adv.json()["data"]["status"] == "approved"
    adv2 = client.post(f"/api/v1/settlements/{data['id']}/advance", headers=hok)
    assert adv2.json()["data"]["status"] == "paid"
    assert adv2.json()["data"]["paid_at"] is not None
    adv3 = client.post(f"/api/v1/settlements/{data['id']}/advance", headers=hok)
    assert adv3.status_code == 409


def test_accounting_requires_permission():
    user, _ = grant(_phone(), "consultant")
    denied = client.post(
        "/api/v1/journal-entries",
        json={"lines": _balanced_lines(1000)},
        headers=h(user),
    )
    assert denied.status_code == 403
    denied2 = client.get("/api/v1/accounts", headers=h(user))
    assert denied2.status_code == 403
