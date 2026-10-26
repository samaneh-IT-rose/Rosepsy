"""Wallet API (B18): view balance/ledger, pay an order from credit,
finance credits (adjustments/topups) with Idempotency-Key."""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.core import User
from app.models.finance import Order, Payment, Wallet, WalletEntry
from app.services.authz import write_audit
from app.services.invoicing import create_invoice_for_order
from app.services.notifications import enqueue_event
from app.services.wallet import (
    credit_wallet,
    debit_wallet,
    entry_data,
    get_or_create_wallet,
    wallet_balance,
    wallet_data,
)

router = APIRouter(tags=["wallet"])


class WalletPayIn(BaseModel):
    order_id: uuid.UUID


class WalletCreditIn(BaseModel):
    user_id: uuid.UUID
    amount: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=300)


@router.get("/wallet")
def get_wallet(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = get_or_create_wallet(db, user.id)
    return envelope(data=wallet_data(db, wallet))


@router.get("/wallet/entries")
def list_wallet_entries(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = get_or_create_wallet(db, user.id)
    entries = db.execute(
        select(WalletEntry)
        .where(WalletEntry.wallet_id == wallet.id)
        .order_by(WalletEntry.created_at.desc())
        .limit(100)
    ).scalars().all()
    return envelope(
        data=[entry_data(e) for e in entries],
        extra_meta={"balance": wallet_balance(db, wallet.id), "count": len(entries)},
    )


@router.get("/wallets/{user_id}")
def get_user_wallet(
    user_id: uuid.UUID,
    user: User = Depends(require_permission("wallet.manage")),
    db: Session = Depends(get_db),
):
    wallet = db.execute(select(Wallet).where(Wallet.user_id == user_id)).scalar_one_or_none()
    if wallet is None:
        return error_response("WALLET_NOT_FOUND", "کیف پول برای این کاربر ساخته نشده است", 404)
    return envelope(data=wallet_data(db, wallet))


@router.post("/wallet/credits")
def credit_user_wallet(
    body: WalletCreditIn,
    request: Request,
    user: User = Depends(require_permission("wallet.manage")),
    db: Session = Depends(get_db),
):
    """Finance officer credits a user's wallet (manual topup / adjustment).

    Idempotency-Key header prevents double-crediting on retries (contract s.10).
    """
    idem = (request.headers.get("Idempotency-Key") or "").strip() or None
    if idem and len(idem) > 80:
        return error_response("MISSING_IDEMPOTENCY_KEY", "کلید idempotency نامعتبر است", 400)

    entry = credit_wallet(
        db,
        user_id=body.user_id,
        amount=body.amount,
        entry_type="adjustment",
        note=body.note,
        idempotency_key=idem,
        actor_user_id=user.id,
    )
    db.commit()
    return envelope(data=entry_data(entry))


@router.post("/wallet/pay")
def pay_order_from_wallet(
    body: WalletPayIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pay an awaiting_payment order directly from the wallet balance (B18).

    Same settlement path as the gateway callback: order paid -> appointment
    fulfilled -> invoice -> notification event, all in one transaction.
    """
    order = db.get(Order, body.order_id)
    if order is None or order.user_id != user.id:
        return error_response("ORDER_NOT_FOUND", "سفارش یافت نشد", 404)
    if order.status != "awaiting_payment":
        return error_response(
            "INVALID_ORDER_STATUS", f"سفارش در وضعیت {order.status} قابل پرداخت نیست", 409
        )
    if order.order_type == "wallet_topup":
        return error_response("INVALID_ORDER_STATUS", "شارژ کیف پول با کیف پول ممکن نیست", 409)

    # debit (row-locked; insufficient balance -> 409) then settle, atomically
    entry = debit_wallet(
        db,
        user_id=user.id,
        amount=int(order.amount),
        entry_type="payment",
        order_id=order.id,
        note=f"order:{order.id}",
        actor_user_id=user.id,
    )
    payment = Payment(
        order_id=order.id,
        gateway="wallet",
        gateway_ref=f"wallet-{entry.id}",
        amount=order.amount,
        currency=order.currency,
        status="verified",
    )
    payment.verified_at = payment.created_at
    db.add(payment)
    db.flush()

    order.status = "paid"
    invoice_id = None
    fulfillment = None
    if order.appointment_id is not None:
        from app.models.booking import Appointment
        from app.services.automation import fulfill_paid_appointment

        appt = db.get(Appointment, order.appointment_id)
        if appt is not None and appt.status == "pending_payment":
            appt.status = "confirmed"
            fulfillment = fulfill_paid_appointment(db, appointment=appt)
    invoice = create_invoice_for_order(db, order)
    invoice_id = str(invoice.id)
    # B22: auto-post the balanced journal (wallet payment: liability out, revenue in)
    from app.services.accounting import post_journal

    post_journal(
        db,
        lines=[
            {"account_code": "2100", "debit": int(order.amount)},
            {"account_code": "4000", "credit": int(order.amount)},
        ],
        description="پرداخت خدمت از کیف پول",
        source_type="order_wallet",
        source_id=order.id,
    )
    enqueue_event(
        db,
        user_id=order.user_id,
        event_type="payment.success",
        payload={"order_id": str(order.id), "amount": int(order.amount)},
    )
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="wallet.pay",
        outcome="allowed",
        resource_type="order",
        resource_id=order.id,
        request_id=request_id_var.get(),
        detail={"amount": int(order.amount)},
    )
    return envelope(
        data={
            "order_id": str(order.id),
            "order_status": order.status,
            "invoice_id": invoice_id,
            "fulfillment": fulfillment,
            "balance_after": int(entry.balance_after),
        }
    )
