"""Discount service (B19): server-side caps, atomic redemption with row lock.

Spec acceptance: simultaneous redemptions must never exceed the cap
(«مصرف هم‌زمان بیش از سقف پذیرفته نشود»). The discount row is locked with
SELECT ... FOR UPDATE while counting redemptions and inserting the new one,
so two concurrent orders cannot both pass the check.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import Discount, DiscountRedemption


def _fail(code: str) -> None:
    raise HTTPException(status_code=422, detail=code)


def quote_discount(
    db: Session, *, code: str, user_id: uuid.UUID, base_amount: int
) -> tuple[Discount, int]:
    """Validate the code against all rules and return (discount, discount_amount)."""
    d = db.execute(
        select(Discount).where(Discount.code == code.strip().upper())
    ).scalar_one_or_none()
    if d is None:
        _fail("DISCOUNT_NOT_FOUND")
    if not d.is_active:
        _fail("DISCOUNT_INACTIVE")

    now = datetime.now(UTC)
    if d.starts_at is not None and now < d.starts_at:
        _fail("DISCOUNT_NOT_STARTED")
    if d.ends_at is not None and now > d.ends_at:
        _fail("DISCOUNT_EXPIRED")

    if base_amount < int(d.min_order_amount or 0):
        _fail("DISCOUNT_MIN_AMOUNT")

    if (
        d.max_redemptions_total is not None
        and db.execute(
            select(func.count())
            .select_from(DiscountRedemption)
            .where(DiscountRedemption.discount_id == d.id)
        ).scalar_one()
        >= d.max_redemptions_total
    ):
        _fail("DISCOUNT_CAP_REACHED")

    if (
        d.max_redemptions_per_user is not None
        and db.execute(
            select(func.count())
            .select_from(DiscountRedemption)
            .where(
                DiscountRedemption.discount_id == d.id,
                DiscountRedemption.user_id == user_id,
            )
        ).scalar_one()
        >= d.max_redemptions_per_user
    ):
        _fail("DISCOUNT_USER_CAP_REACHED")

    if d.kind == "percent":
        amount = min(int(base_amount * int(d.value) / 100), base_amount)
    else:
        amount = min(int(d.value), base_amount)
    return d, amount


def apply_discount_to_order(
    db: Session,
    *,
    code: str,
    user_id: uuid.UUID,
    base_amount: int,
    order_id: uuid.UUID,
) -> tuple[Discount, int]:
    """Lock the discount row, re-validate, and persist the redemption.

    Must be called INSIDE the order-creation transaction (no commit here).
    """
    # lock the code row to serialize concurrent redemptions
    locked = db.execute(
        select(Discount).where(Discount.code == code.strip().upper()).with_for_update()
    ).scalar_one_or_none()
    if locked is None:
        _fail("DISCOUNT_NOT_FOUND")

    discount, amount = quote_discount(db, code=code, user_id=user_id, base_amount=base_amount)
    if amount <= 0:
        _fail("DISCOUNT_NOT_APPLICABLE")

    db.add(
        DiscountRedemption(
            discount_id=discount.id,
            user_id=user_id,
            order_id=order_id,
            amount_applied=amount,
        )
    )
    db.flush()
    return discount, amount


def release_order_redemption(db: Session, *, order_id: uuid.UUID) -> None:
    """Free the redeemed cap slot when the order is cancelled before payment."""
    redemption = db.execute(
        select(DiscountRedemption).where(DiscountRedemption.order_id == order_id)
    ).scalar_one_or_none()
    if redemption is not None:
        db.delete(redemption)
        db.flush()


def discount_data(d: Discount) -> dict:
    return {
        "id": str(d.id),
        "code": d.code,
        "kind": d.kind,
        "value": int(d.value),
        "min_order_amount": int(d.min_order_amount or 0),
        "max_redemptions_total": d.max_redemptions_total,
        "max_redemptions_per_user": d.max_redemptions_per_user,
        "starts_at": d.starts_at.isoformat() if d.starts_at else None,
        "ends_at": d.ends_at.isoformat() if d.ends_at else None,
        "is_active": d.is_active,
        "created_at": d.created_at.isoformat(),
    }
