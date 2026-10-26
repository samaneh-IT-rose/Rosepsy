"""Refund API (B20): user submits, finance reviews/approves/rejects/executes."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.finance import Order, Refund, RefundRequest
from app.services.authz import has_permission
from app.services.refunds import (
    _request_data,
    approve_refund,
    execute_refund,
    reject_refund,
    review_refund,
    submit_refund_request,
)

router = APIRouter(tags=["refunds"])


class RefundRequestIn(BaseModel):
    order_id: uuid.UUID
    amount: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)


class RefundDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


@router.post("/refund-requests", status_code=201)
def create_refund_request(
    body: RefundRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, body.order_id)
    if order is None or order.user_id != user.id:
        return error_response("ORDER_NOT_FOUND", "سفارش یافت نشد", 404)
    request = submit_refund_request(
        db,
        order=order,
        user_id=user.id,
        amount=body.amount,
        reason=body.reason,
    )
    db.commit()
    return envelope(data=_request_data(request))


@router.get("/refund-requests")
def list_refund_requests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if has_permission(db, user.id, "refunds.manage"):
        rows = db.execute(
            select(RefundRequest).order_by(RefundRequest.created_at.desc()).limit(200)
        ).scalars().all()
    else:
        rows = db.execute(
            select(RefundRequest)
            .where(RefundRequest.user_id == user.id)
            .order_by(RefundRequest.created_at.desc())
            .limit(100)
        ).scalars().all()
    executed = {
        r.refund_request_id: int(r.amount)
        for r in db.execute(select(Refund)).scalars().all()
    }
    return envelope(
        data=[_request_data(r, executed.get(r.id)) for r in rows]
    )


@router.post("/refund-requests/{request_id}/review")
def review(
    request_id: uuid.UUID,
    user: User = Depends(require_permission("refunds.manage")),
    db: Session = Depends(get_db),
):
    request = db.get(RefundRequest, request_id)
    if request is None:
        return error_response("REFUND_REQUEST_NOT_FOUND", "درخواست استرداد یافت نشد", 404)
    review_refund(db, request, actor_user_id=user.id)
    db.commit()
    return envelope(data=_request_data(request))


@router.post("/refund-requests/{request_id}/approve")
def approve(
    request_id: uuid.UUID,
    body: RefundDecisionIn | None = None,
    user: User = Depends(require_permission("refunds.manage")),
    db: Session = Depends(get_db),
):
    request = db.get(RefundRequest, request_id)
    if request is None:
        return error_response("REFUND_REQUEST_NOT_FOUND", "درخواست استرداد یافت نشد", 404)
    approve_refund(
        db, request, actor_user_id=user.id, note=body.note if body else None
    )
    db.commit()
    return envelope(data=_request_data(request))


@router.post("/refund-requests/{request_id}/reject")
def reject(
    request_id: uuid.UUID,
    body: RefundDecisionIn,
    user: User = Depends(require_permission("refunds.manage")),
    db: Session = Depends(get_db),
):
    request = db.get(RefundRequest, request_id)
    if request is None:
        return error_response("REFUND_REQUEST_NOT_FOUND", "درخواست استرداد یافت نشد", 404)
    reject_refund(
        db, request, actor_user_id=user.id, note=body.note or "رد درخواست استرداد"
    )
    db.commit()
    return envelope(data=_request_data(request))


@router.post("/refund-requests/{request_id}/execute")
def execute(
    request_id: uuid.UUID,
    user: User = Depends(require_permission("refunds.manage")),
    db: Session = Depends(get_db),
):
    request = db.get(RefundRequest, request_id)
    if request is None:
        return error_response("REFUND_REQUEST_NOT_FOUND", "درخواست استرداد یافت نشد", 404)
    refund = execute_refund(db, request, actor_user_id=user.id)
    db.commit()
    return envelope(
        data={
            "id": str(refund.id),
            "refund_request_id": str(refund.refund_request_id),
            "amount": int(refund.amount),
            "executed_at": refund.executed_at.isoformat(),
            "request_status": request.status,
        }
    )
