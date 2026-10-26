"""Refund service (B20): state machine submitted -> reviewing -> approved -> executed.

Rules (spec BPMN 05 + s.09a):
- refundable amount = paid amount - already executed refunds (no over-refund)
- only one ACTIVE request per order at a time
- execution returns the money to the user's wallet (B18) and is unique per request
- transition violations are rejected with 409 (never silently)
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Order, Refund, RefundRequest
from app.services.authz import write_audit
from app.services.wallet import credit_wallet

ACTIVE_REFUND_STATUSES = ("submitted", "reviewing", "approved")


def refunded_total(db: Session, order_id: uuid.UUID) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.refund_request_id.in_(
                select(RefundRequest.id).where(RefundRequest.order_id == order_id)
            )
        )
    ).scalar_one()
    return int(total)


def _request_data(r: RefundRequest, executed_amount: int | None = None) -> dict:
    data = {
        "id": str(r.id),
        "order_id": str(r.order_id),
        "user_id": str(r.user_id),
        "amount": int(r.amount),
        "reason": r.reason,
        "status": r.status,
        "decision_note": r.decision_note,
        "created_at": r.created_at.isoformat(),
    }
    if executed_amount is not None:
        data["executed_amount"] = executed_amount
    return data


def submit_refund_request(
    db: Session,
    *,
    order: Order,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
) -> RefundRequest:
    if order.status != "paid":
        raise HTTPException(status_code=409, detail="REFUND_ORDER_NOT_PAID")
    if amount <= 0 or amount > int(order.amount):
        raise HTTPException(status_code=422, detail="REFUND_AMOUNT_INVALID")

    refunded = refunded_total(db, order.id)
    if amount > int(order.amount) - refunded:
        raise HTTPException(status_code=409, detail="REFUND_EXCEEDS_REMAINING")

    active = db.execute(
        select(RefundRequest)
        .where(
            RefundRequest.order_id == order.id,
            RefundRequest.status.in_(ACTIVE_REFUND_STATUSES),
        )
        .limit(1)
    ).scalar_one_or_none()
    if active is not None:
        raise HTTPException(status_code=409, detail="REFUND_REQUEST_EXISTS")

    request = RefundRequest(
        order_id=order.id,
        user_id=user_id,
        amount=amount,
        reason=(reason or "")[:500],
        status="submitted",
    )
    db.add(request)
    db.flush()
    write_audit(
        db,
        actor_user_id=user_id,
        action="refund.request",
        outcome="allowed",
        resource_type="refund_request",
        resource_id=request.id,
        detail={"order_id": str(order.id), "amount": amount},
    )
    return request


def _transition(
    db: Session,
    request: RefundRequest,
    *,
    from_status: str,
    to_status: str,
    actor_user_id: uuid.UUID,
    note: str | None = None,
) -> RefundRequest:
    if request.status != from_status:
        raise HTTPException(
            status_code=409,
            detail=f"INVALID_REFUND_TRANSITION|{request.status}->{to_status}",
        )
    request.status = to_status
    request.decided_by = actor_user_id
    if note is not None:
        request.decision_note = note[:500]
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action=f"refund.{to_status}",
        outcome="allowed",
        resource_type="refund_request",
        resource_id=request.id,
        detail={"from": from_status},
    )
    return request


def review_refund(db: Session, request: RefundRequest, actor_user_id: uuid.UUID) -> RefundRequest:
    return _transition(
        db, request, from_status="submitted", to_status="reviewing", actor_user_id=actor_user_id
    )


def approve_refund(
    db: Session,
    request: RefundRequest,
    actor_user_id: uuid.UUID,
    note: str | None = None,
) -> RefundRequest:
    return _transition(
        db,
        request,
        from_status="reviewing",
        to_status="approved",
        actor_user_id=actor_user_id,
        note=note,
    )


def reject_refund(
    db: Session, request: RefundRequest, actor_user_id: uuid.UUID, note: str
) -> RefundRequest:
    if request.status not in ("submitted", "reviewing"):
        raise HTTPException(status_code=409, detail="INVALID_REFUND_TRANSITION")
    request.status = "rejected"
    request.decided_by = actor_user_id
    request.decision_note = (note or "")[:500]
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="refund.rejected",
        outcome="allowed",
        resource_type="refund_request",
        resource_id=request.id,
    )
    return request


def execute_refund(db: Session, request: RefundRequest, actor_user_id: uuid.UUID) -> Refund:
    """Execute an approved refund: wallet credit + immutable refund record.

    Order becomes 'refunded' once the cumulative refunds reach its amount.
    """
    existing = db.execute(
        select(Refund).where(Refund.refund_request_id == request.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="REFUND_ALREADY_EXECUTED")

    if request.status != "approved":
        raise HTTPException(status_code=409, detail="REFUND_NOT_APPROVED")

    order = db.get(Order, request.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")

    entry = credit_wallet(
        db,
        user_id=request.user_id,
        amount=int(request.amount),
        entry_type="refund",
        order_id=order.id,
        note=f"refund:{request.id}",
    )
    refund = Refund(
        refund_request_id=request.id,
        payment_id=None,
        wallet_entry_id=entry.id,
        amount=request.amount,
        executed_by=actor_user_id,
    )
    db.add(refund)
    db.flush()

    if refunded_total(db, order.id) >= int(order.amount) and order.status == "paid":
        order.status = "refunded"

    request.status = "executed"
    request.decided_by = actor_user_id
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="refund.executed",
        outcome="allowed",
        resource_type="refund",
        resource_id=refund.id,
        detail={"order_id": str(order.id), "amount": int(request.amount)},
    )
    return refund
