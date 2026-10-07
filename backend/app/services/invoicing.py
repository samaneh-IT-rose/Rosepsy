"""Invoice creation (B11): unique number from a DB sequence, amount = order snapshot."""

from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.booking import Appointment
from app.models.catalog import Service
from app.models.finance import Invoice, InvoiceItem, Order


def next_invoice_number(db: Session) -> str:
    # self-healing: guarantees the sequence even if the migration went the stamp path
    db.execute(text("CREATE SEQUENCE IF NOT EXISTS finance.invoice_number_seq START 1"))
    seq = db.execute(text("SELECT nextval('finance.invoice_number_seq')")).scalar_one()
    year = datetime.now(UTC).year
    return f"INV-{year}-{seq:06d}"


def create_invoice_for_order(db: Session, order: Order) -> Invoice:
    """Idempotent: returns the existing invoice if the order already has one."""
    existing = db.execute(
        select(Invoice).where(Invoice.order_id == order.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    description = "سفارش خدمات کلینیک رز"
    if order.appointment_id is not None:
        appt = db.get(Appointment, order.appointment_id)
        if appt is not None:
            svc = db.get(Service, appt.service_id)
            if svc is not None:
                description = svc.name

    invoice = Invoice(
        order_id=order.id,
        invoice_number=next_invoice_number(db),
        amount=order.amount,
        currency=order.currency,
    )
    db.add(invoice)
    db.flush()
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            description=description[:200],
            quantity=1,
            unit_amount=order.amount,
            total=order.amount,
        )
    )
    return invoice
