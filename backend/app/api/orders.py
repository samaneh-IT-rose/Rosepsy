import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.booking import Appointment
from app.models.core import User
from app.models.finance import Order, Payment
from app.services.authz import has_permission, write_audit
from app.services.automation import fulfill_paid_appointment
from app.services.gateway import get_gateway
from app.services.notifications import enqueue_event

router = APIRouter(tags=["orders", "payments"])

ACTIVE_ORDER_STATUSES = ("draft", "awaiting_payment", "paid")


class OrderIn(BaseModel):
    appointment_id: uuid.UUID


class PaymentStartIn(BaseModel):
    order_id: uuid.UUID


class CallbackIn(BaseModel):
    gateway_ref: str = Field(min_length=4, max_length=64)
    result: str = Field(pattern=r"^(success|failure)$")


def _order_data(o: Order) -> dict:
    return {
        "id": str(o.id),
        "user_id": str(o.user_id),
        "appointment_id": str(o.appointment_id) if o.appointment_id else None,
        "order_type": o.order_type,
        "amount": int(o.amount),
        "currency": o.currency,
        "status": o.status,
        "price_snapshot": o.price_snapshot,
        "created_at": o.created_at.isoformat(),
    }


@router.post("/orders", status_code=201)
def create_order(
    body: OrderIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a payment order for a pending appointment (B10).

    Requires the Idempotency-Key header (contract s.10); repeated calls with
    the same key return the same order instead of creating a duplicate.
    """
    idem = (request.headers.get("Idempotency-Key") or "").strip()
    if not idem or len(idem) > 80:
        return error_response("MISSING_IDEMPOTENCY_KEY", "هدر Idempotency-Key الزامی است", 400)

    replay = db.execute(
        select(Order).where(Order.user_id == user.id, Order.idempotency_key == idem)
    ).scalar_one_or_none()
    if replay is not None:
        return JSONResponse(
            status_code=200,
            content=envelope(data=_order_data(replay), extra_meta={"idempotent_replay": True}),
        )

    appt = db.get(Appointment, body.appointment_id)
    if appt is None or appt.user_id != user.id:
        return error_response("APPOINTMENT_NOT_FOUND", "نوبت یافت نشد", 404)
    if appt.status != "pending_payment":
        return error_response(
            "INVALID_APPOINTMENT_STATUS", f"نوبت در وضعیت {appt.status} قابل پرداخت نیست", 409
        )
    snapshot = appt.price_snapshot
    if not snapshot or int(snapshot.get("amount", 0)) <= 0:
        return error_response("NOTHING_TO_PAY", "این نوبت هزینه‌ای برای پرداخت ندارد", 409)

    active = db.execute(
        select(Order).where(
            Order.appointment_id == appt.id, Order.status.in_(ACTIVE_ORDER_STATUSES)
        )
    ).scalar_one_or_none()
    if active is not None:
        return error_response(
            "ORDER_EXISTS",
            "برای این نوبت سفارش فعال وجود دارد",
            409,
            details={"order_id": str(active.id)},
        )

    order = Order(
        user_id=user.id,
        appointment_id=appt.id,
        order_type="appointment",
        amount=int(snapshot["amount"]),
        currency=snapshot.get("currency", "IRR"),
        status="awaiting_payment",
        idempotency_key=idem,
        price_snapshot=snapshot,
    )
    db.add(order)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="order.create",
        outcome="allowed",
        resource_type="order",
        resource_id=order.id,
        request_id=request_id_var.get(),
        detail={"amount": int(order.amount)},
    )
    return JSONResponse(status_code=201, content=envelope(data=_order_data(order)))


@router.get("/orders/{order_id}")
def get_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None:
        return error_response("ORDER_NOT_FOUND", "سفارش یافت نشد", 404)
    if order.user_id != user.id and not has_permission(db, user.id, "orders.read"):
        return error_response("ORDER_NOT_FOUND", "سفارش یافت نشد", 404)
    return envelope(data=_order_data(order))


@router.post("/payments/start")
def start_payment(
    body: PaymentStartIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, body.order_id)
    if order is None or order.user_id != user.id:
        return error_response("ORDER_NOT_FOUND", "سفارش یافت نشد", 404)
    if order.status != "awaiting_payment":
        return error_response(
            "INVALID_ORDER_STATUS", f"سفارش در وضعیت {order.status} قابل پرداخت نیست", 409
        )
    in_progress = db.execute(
        select(Payment).where(Payment.order_id == order.id, Payment.status == "initiated")
    ).scalar_one_or_none()
    if in_progress is not None:
        return error_response(
            "PAYMENT_IN_PROGRESS", "یک پرداخت فعال برای این سفارش وجود دارد", 409
        )

    gateway = get_gateway()
    ref, url = gateway.start(order_id=order.id, amount=int(order.amount), currency=order.currency)
    payment = Payment(
        order_id=order.id,
        gateway=gateway.name,
        gateway_ref=ref,
        amount=order.amount,
        currency=order.currency,
    )
    db.add(payment)
    db.commit()
    return envelope(
        data={
            "payment_id": str(payment.id),
            "order_id": str(order.id),
            "gateway_ref": ref,
            "redirect_url": url,
        }
    )


@router.post("/payments/callback")
def payments_callback(
    body: CallbackIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Gateway server-to-server callback (B10).

    - restricted to gateway IPs via PAYMENT_CALLBACK_ALLOWLIST (empty = dev only)
    - final state only after server-side verification via the gateway adapter
    - repeated callbacks are a no-op (spec: callback تکراری بی‌اثر)
    """
    allowlist = [ip.strip() for ip in settings.PAYMENT_CALLBACK_ALLOWLIST.split(",") if ip.strip()]
    client_ip = request.client.host if request.client else "-"
    if allowlist and client_ip not in allowlist:
        write_audit(
            db,
            action="payments.callback",
            outcome="denied",
            request_id=request_id_var.get(),
            detail={"ip": client_ip},
        )
        return error_response("FORBIDDEN", "دسترسی درگاه مجاز نیست", 403)

    payment = db.execute(
        select(Payment).where(Payment.gateway_ref == body.gateway_ref)
    ).scalar_one_or_none()
    if payment is None:
        return error_response("PAYMENT_NOT_FOUND", "پرداخت یافت نشد", 404)
    if payment.status != "initiated":
        return envelope(
            data={"payment_id": str(payment.id), "status": payment.status, "noop": True}
        )

    gateway = get_gateway()
    ok, raw = gateway.verify(payload=body.model_dump())
    payment.raw_callback = raw
    order = db.get(Order, payment.order_id)
    invoice_id = None
    fulfillment = None
    if ok:
        payment.status = "verified"
        payment.verified_at = datetime.now(UTC)
        order.status = "paid"
        if order.appointment_id is not None:
            appt = db.get(Appointment, order.appointment_id)
            if appt is not None and appt.status == "pending_payment":
                appt.status = "confirmed"
                fulfillment = fulfill_paid_appointment(db, appointment=appt)
        from app.services.invoicing import create_invoice_for_order

        invoice = create_invoice_for_order(db, order)
        invoice_id = str(invoice.id)
        enqueue_event(
            db,
            user_id=order.user_id,
            event_type="payment.success",
            payload={"order_id": str(order.id), "amount": int(order.amount)},
        )
    else:
        payment.status = "failed"
        order.status = "failed"
    db.commit()
    write_audit(
        db,
        action="payments.callback",
        outcome="allowed",
        resource_type="order",
        resource_id=order.id,
        request_id=request_id_var.get(),
        detail={"result": body.result, "order_status": order.status},
    )
    return envelope(
        data={
            "payment_id": str(payment.id),
            "order_id": str(order.id),
            "order_status": order.status,
            "invoice_id": invoice_id,
            "fulfillment": fulfillment,
            "noop": False,
        }
    )


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: uuid.UUID,
    user: User = Depends(require_permission("orders.read")),
    db: Session = Depends(get_db),
):
    payment = db.get(Payment, payment_id)
    if payment is None:
        return error_response("PAYMENT_NOT_FOUND", "پرداخت یافت نشد", 404)
    return envelope(
        data={
            "id": str(payment.id),
            "order_id": str(payment.order_id),
            "gateway": payment.gateway,
            "gateway_ref": payment.gateway_ref,
            "amount": int(payment.amount),
            "currency": payment.currency,
            "status": payment.status,
        }
    )
