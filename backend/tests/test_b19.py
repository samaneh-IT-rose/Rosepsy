"""B19 — Discounts: caps, windows, min amount, per-user cap, order integration."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.db import engine
from tests.helpers import client, grant, h
from tests.test_b18 import _make_pending_appointment_and_order

PHONE = iter(range(9142020000, 9142029999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _mk_discount(hok, **kw) -> dict:
    body = {
        "code": kw.pop("code", f"ROSE{uuid.uuid4().hex[:6].upper()}"),
        "kind": kw.pop("kind", "fixed"),
        "value": kw.pop("value", 500000),
    }
    body.update(kw)
    for k in ("starts_at", "ends_at"):
        if k in body and hasattr(body[k], "isoformat"):
            body[k] = body[k].isoformat()
    r = client.post("/api/v1/discounts", json=body, headers=hok)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_create_discount_validation_and_list():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    d = _mk_discount(hok, max_redemptions_total=2)
    assert d["is_active"] is True

    # duplicate code
    dup = client.post(
        "/api/v1/discounts",
        json={"code": d["code"], "kind": "fixed", "value": 1000},
        headers=hok,
    )
    assert dup.status_code == 409

    # percent > 100 invalid
    bad = client.post(
        "/api/v1/discounts",
        json={"code": "PCT200", "kind": "percent", "value": 200},
        headers=hok,
    )
    assert bad.status_code == 422

    # non-manager denied
    user, _ = grant(_phone(), "consultant")
    denied = client.post(
        "/api/v1/discounts",
        json={"code": "NOPER", "kind": "fixed", "value": 100},
        headers=h(user),
    )
    assert denied.status_code == 403

    listed = client.get("/api/v1/discounts", headers=hok).json()["data"]
    assert any(x["code"] == d["code"] for x in listed)


def test_validate_endpoint_quotes_without_consuming():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    d = _mk_discount(hok, value=300000, max_redemptions_total=1)
    v = client.post(
        "/api/v1/discounts/validate",
        json={"code": d["code"], "base_amount": 4500000},
        headers=hok,
    )
    assert v.status_code == 200, v.text
    assert v.json()["data"]["discount_amount"] == 300000
    assert v.json()["data"]["payable_amount"] == 4200000

    unknown = client.post(
        "/api/v1/discounts/validate",
        json={"code": "NOPE123", "base_amount": 1000},
        headers=hok,
    )
    assert unknown.status_code == 422
    assert unknown.json()["errors"][0]["code"] == "DISCOUNT_NOT_FOUND"


def test_discount_applied_to_order_reduces_amount():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    d = _mk_discount(hok, value=500000)
    _, order = _make_pending_appointment_and_order(hok, discount=d["code"])
    assert order["amount"] == 4000000  # 4.5M - 0.5M
    assert order["discount_amount"] == 500000
    assert order["discount_id"] == d["id"]

    # no discount on second order for same appointment flow: base amount used
    _, order2 = _make_pending_appointment_and_order(hok)
    assert order2["amount"] == 4500000


def test_expired_and_min_amount_rules():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    expired = _mk_discount(
        hok,
        starts_at=datetime.now(UTC) - timedelta(days=10),
        ends_at=datetime.now(UTC) - timedelta(days=1),
    )
    v = client.post(
        "/api/v1/discounts/validate",
        json={"code": expired["code"], "base_amount": 4500000},
        headers=hok,
    )
    assert v.status_code == 422
    assert v.json()["errors"][0]["code"] == "DISCOUNT_EXPIRED"

    future = _mk_discount(
        hok,
        starts_at=datetime.now(UTC) + timedelta(days=5),
        ends_at=datetime.now(UTC) + timedelta(days=9),
    )
    v2 = client.post(
        "/api/v1/discounts/validate",
        json={"code": future["code"], "base_amount": 4500000},
        headers=hok,
    )
    assert v2.json()["errors"][0]["code"] == "DISCOUNT_NOT_STARTED"

    mind = _mk_discount(hok, value=100000, min_order_amount=1000000)
    v3 = client.post(
        "/api/v1/discounts/validate",
        json={"code": mind["code"], "base_amount": 500000},
        headers=hok,
    )
    assert v3.json()["errors"][0]["code"] == "DISCOUNT_MIN_AMOUNT"

    inactive = _mk_discount(hok, is_active=False)
    v4 = client.post(
        "/api/v1/discounts/validate",
        json={"code": inactive["code"], "base_amount": 500000},
        headers=hok,
    )
    assert v4.json()["errors"][0]["code"] == "DISCOUNT_INACTIVE"


def test_total_cap_enforced_across_users():
    admin, _ = grant(_phone(), "system_admin")
    hadmin = h(admin)
    d = _mk_discount(hadmin, value=200000, max_redemptions_total=1)

    user1, uid1 = grant(_phone(), "consultant")
    user2, _ = grant(_phone(), "consultant")

    _, order1 = _make_pending_appointment_and_order(hadmin, discount=d["code"], book_with=h(user1))
    assert order1["amount"] == 4300000

    # second user: cap reached (order creation fails with 422)
    appt2, _ = _make_pending_appointment_and_order(hadmin, book_with=h(user2), slot_minute=45)
    r2 = client.post(
        "/api/v1/orders",
        json={"appointment_id": appt2["id"], "discount_code": d["code"]},
        headers={**h(user2), "Idempotency-Key": f"ord-{uuid.uuid4().hex[:10]}"},
    )
    assert r2.status_code == 422, r2.text
    assert r2.json()["errors"][0]["code"] == "DISCOUNT_CAP_REACHED"


def test_per_user_cap_enforced():
    admin, _ = grant(_phone(), "system_admin")
    hadmin = h(admin)
    d = _mk_discount(hadmin, value=100000, max_redemptions_per_user=1)

    user1, _ = grant(_phone(), "consultant")
    huser = h(user1)
    _make_pending_appointment_and_order(hadmin, discount=d["code"], book_with=huser)
    appt2, _ = _make_pending_appointment_and_order(hadmin, book_with=huser, slot_minute=45)
    r2 = client.post(
        "/api/v1/orders",
        json={"appointment_id": appt2["id"], "discount_code": d["code"]},
        headers={**huser, "Idempotency-Key": f"ord-{uuid.uuid4().hex[:10]}"},
    )
    assert r2.status_code == 422
    assert r2.json()["errors"][0]["code"] == "DISCOUNT_USER_CAP_REACHED"


def test_percent_discount_caps_at_order_amount():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    d = _mk_discount(hok, kind="percent", value=50)
    v = client.post(
        "/api/v1/discounts/validate",
        json={"code": d["code"], "base_amount": 4500000},
        headers=hok,
    )
    assert v.json()["data"]["discount_amount"] == 2250000
    assert v.json()["data"]["payable_amount"] == 2250000


def test_redemption_count_matches_orders():
    token, uid = grant(_phone(), "system_admin")
    hok = h(token)
    d = _mk_discount(hok, value=100000)
    _make_pending_appointment_and_order(hok, discount=d["code"])
    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM finance.discount_redemptions WHERE discount_id = :d"),
            {"d": uuid.UUID(d["id"])},
        ).scalar_one()
    assert n == 1
