"""B24 — Manager dashboard: KPI aggregation + RBAC."""


from tests.helpers import client, grant, h
from tests.test_b18 import _make_pending_appointment_and_order

PHONE = iter(range(9142070000, 9142079999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def test_manager_dashboard_requires_permission():
    user, _ = grant(_phone(), "consultant")
    denied = client.get("/api/v1/dashboards/manager", headers=h(user))
    assert denied.status_code == 403


def test_manager_dashboard_aggregates():
    admin, _ = grant(_phone(), "system_admin")
    hok = h(admin)
    # one paid appointment order + one topup
    _, order = _make_pending_appointment_and_order(hok)
    start = client.post(
        "/api/v1/payments/start", json={"order_id": order["id"]}, headers=hok
    ).json()["data"]
    client.post(
        "/api/v1/payments/callback",
        json={"gateway_ref": start["gateway_ref"], "result": "success"},
        headers=hok,
    )

    d = client.get("/api/v1/dashboards/manager", headers=hok)
    assert d.status_code == 200, d.text
    data = d.json()["data"]

    assert data["appointments_by_status"].get("confirmed", 0) >= 1
    assert data["orders"]["paid_count"] >= 1
    assert data["orders"]["gross_amount"] >= 4500000
    assert data["orders"]["net_amount"] == (
        data["orders"]["gross_amount"] - data["orders"]["refunded_amount"]
    )
    assert len(data["revenue_by_day_7d"]) >= 1
    assert data["kpis"]["consultants"] >= 1
    assert data["kpis"]["users"] >= 1
    assert data["kpis"]["invoices"] >= 1
    assert any(
        s["bookings"] >= 1 for s in data["top_services"]
    ) or data["top_services"] == []
