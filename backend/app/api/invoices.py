import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.finance import Invoice, InvoiceItem, Order
from app.services.authz import has_permission
from app.services.pdf import simple_pdf

router = APIRouter(tags=["invoices"])


def _load(db: Session, invoice_id: uuid.UUID) -> tuple[Invoice | None, Order | None]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        return None, None
    order = db.get(Order, invoice.order_id)
    return invoice, order


def _can_view(db: Session, user: User, order: Order | None) -> bool:
    if order is None:
        return False
    return order.user_id == user.id or has_permission(db, user.id, "invoices.read")


def _invoice_data(db: Session, invoice: Invoice) -> dict:
    items = (
        db.execute(
            select(InvoiceItem)
            .where(InvoiceItem.invoice_id == invoice.id)
            .order_by(InvoiceItem.id)
        )
        .scalars()
        .all()
    )
    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "order_id": str(invoice.order_id),
        "amount": int(invoice.amount),
        "currency": invoice.currency,
        "issued_at": invoice.issued_at.isoformat(),
        "items": [
            {
                "description": it.description,
                "quantity": it.quantity,
                "unit_amount": int(it.unit_amount),
                "total": int(it.total),
            }
            for it in items
        ],
    }


@router.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice, order = _load(db, invoice_id)
    if invoice is None or not _can_view(db, user, order):
        return error_response("INVOICE_NOT_FOUND", "فاکتور یافت نشد", 404)
    return envelope(data=_invoice_data(db, invoice))


@router.get("/invoices/{invoice_id}.pdf")
def get_invoice_pdf(
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice, order = _load(db, invoice_id)
    if invoice is None or not _can_view(db, user, order):
        return error_response("INVOICE_NOT_FOUND", "فاکتور یافت نشد", 404)
    lines = [
        "Roz Clinic - Invoice",
        f"Invoice No: {invoice.invoice_number}",
        f"Order: {invoice.order_id}",
        f"Amount: {int(invoice.amount)} {invoice.currency}",
        "Status: PAID",
        f"Issued (UTC): {invoice.issued_at.isoformat()}",
        "",
        "(Persian-formatted PDF is planned for the UI release)",
    ]
    return Response(
        content=simple_pdf(lines),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"'},
    )
