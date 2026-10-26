"""Discount API (B19): manage codes (finance) and validate a code (user)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.finance import Discount
from app.services.authz import write_audit
from app.services.discounts import discount_data, quote_discount

router = APIRouter(tags=["discounts"])


class DiscountIn(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: str = Field(pattern=r"^(percent|fixed)$")
    value: int = Field(gt=0)
    min_order_amount: int = Field(default=0, ge=0)
    max_redemptions_total: int | None = Field(default=None, ge=1)
    max_redemptions_per_user: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True


class DiscountValidateIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    base_amount: int = Field(gt=0)


@router.post("/discounts", status_code=201)
def create_discount(
    body: DiscountIn,
    user: User = Depends(require_permission("discounts.manage")),
    db: Session = Depends(get_db),
):
    if body.kind == "percent" and body.value > 100:
        return error_response("DISCOUNT_VALUE_INVALID", "درصد تخفیف باید بین ۱ تا ۱۰۰ باشد", 422)
    if body.ends_at is not None and body.starts_at is not None and body.ends_at <= body.starts_at:
        return error_response("DISCOUNT_WINDOW_INVALID", "بازه اعتبار تخفیف نامعتبر است", 422)

    exists = db.execute(
        select(Discount).where(Discount.code == body.code.upper())
    ).scalar_one_or_none()
    if exists is not None:
        return error_response("DISCOUNT_CODE_EXISTS", "این کد تخفیف قبلاً ثبت شده است", 409)

    d = Discount(
        code=body.code.upper(),
        kind=body.kind,
        value=body.value,
        min_order_amount=body.min_order_amount,
        max_redemptions_total=body.max_redemptions_total,
        max_redemptions_per_user=body.max_redemptions_per_user,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        is_active=body.is_active,
        created_by=user.id,
    )
    db.add(d)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="discount.create",
        outcome="allowed",
        resource_type="discount",
        resource_id=d.id,
        detail={"code": d.code},
    )
    return envelope(data=discount_data(d))


@router.get("/discounts")
def list_discounts(
    user: User = Depends(require_permission("discounts.manage")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Discount).order_by(Discount.created_at.desc()).limit(200)
    ).scalars().all()
    return envelope(data=[discount_data(d) for d in rows])


@router.post("/discounts/validate")
def validate_discount(
    body: DiscountValidateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quote without applying (does not consume a redemption slot)."""
    try:
        d, amount = quote_discount(
            db, code=body.code, user_id=user.id, base_amount=body.base_amount
        )
    except HTTPException as exc:
        code = str(exc.detail)
        messages = {
            "DISCOUNT_NOT_FOUND": "کد تخفیف یافت نشد",
            "DISCOUNT_INACTIVE": "کد تخفیف غیرفعال است",
            "DISCOUNT_NOT_STARTED": "کد تخفیف هنوز شروع نشده است",
            "DISCOUNT_EXPIRED": "کد تخفیف منقضی شده است",
            "DISCOUNT_MIN_AMOUNT": "مبلغ سفارش کمتر از حداقل مجاز است",
            "DISCOUNT_CAP_REACHED": "سقف مصرف کد تخفیف تکمیل شده است",
            "DISCOUNT_USER_CAP_REACHED": "سقف مصرف شما از این کد تکمیل شده است",
            "DISCOUNT_NOT_APPLICABLE": "کد تخفیف برای این سفارش قابل اعمال نیست",
        }
        return error_response(
            code, messages.get(code, "کد تخفیف قابل استفاده نیست"), exc.status_code
        )
    return envelope(
        data={
            "code": d.code,
            "discount_amount": amount,
            "payable_amount": body.base_amount - amount,
        }
    )
