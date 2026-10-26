"""Dashboards API (B24): manager KPIs aggregated from live data."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope
from app.core.db import get_db
from app.models.booking import Appointment
from app.models.catalog import Consultant
from app.models.core import User
from app.models.finance import Invoice, Order, Refund

router = APIRouter(tags=["dashboards"])


@router.get("/dashboards/manager")
def manager_dashboard(
    user: User = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Operational + financial KPIs. Definition note: revenue = paid orders
    (gateway + wallet), refunds are reported separately (spec B24: KPI شفاف)."""
    appt_counts = dict(
        db.execute(
            select(Appointment.status, func.count())
            .group_by(Appointment.status)
        ).all()
    )
    paid_orders = db.execute(
        select(func.count(), func.coalesce(func.sum(Order.amount), 0)).where(
            Order.status.in_(("paid", "refunded"))
        )
    ).one()
    refunded_sum = db.execute(
        select(func.coalesce(func.sum(Refund.amount), 0))
    ).scalar_one()

    since = datetime.now(UTC) - timedelta(days=7)
    revenue_by_day_rows = db.execute(
        select(
            func.date_trunc("day", Order.updated_at).label("day"),
            func.coalesce(func.sum(Order.amount), 0),
        )
        .where(Order.status.in_(("paid", "refunded")), Order.updated_at >= since)
        .group_by("day")
        .order_by("day")
    ).all()

    top_services = db.execute(
        select(Appointment.service_id, func.count().label("bookings"))
        .group_by(Appointment.service_id)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    users_count = db.execute(select(func.count()).select_from(User)).scalar_one()
    consultants_count = db.execute(select(func.count()).select_from(Consultant)).scalar_one()
    invoices_count = db.execute(select(func.count()).select_from(Invoice)).scalar_one()

    return envelope(
        data={
            "appointments_by_status": {k: v for k, v in appt_counts.items()},
            "orders": {
                "paid_count": paid_orders[0],
                "gross_amount": int(paid_orders[1]),
                "refunded_amount": int(refunded_sum),
                "net_amount": int(paid_orders[1]) - int(refunded_sum),
            },
            "revenue_by_day_7d": [
                {"day": day.isoformat(), "amount": int(amount)}
                for day, amount in revenue_by_day_rows
            ],
            "top_services": [
                {"service_id": str(sid), "bookings": n} for sid, n in top_services if sid
            ],
            "kpis": {
                "users": users_count,
                "consultants": consultants_count,
                "invoices": invoices_count,
            },
        }
    )
