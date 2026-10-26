"""Accounting API (B22): accounts, balanced journal entries, settlements."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.catalog import Consultant
from app.models.core import User
from app.models.finance import Account, JournalEntry, Settlement
from app.services.accounting import (
    account_balance,
    journal_data,
    post_journal,
)
from app.services.authz import write_audit

router = APIRouter(tags=["accounting"])

SETTLEMENT_TRANSITIONS = {"draft": "approved", "approved": "paid"}


class AccountIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern=r"^(asset|liability|equity|revenue|expense)$")


class JournalLineIn(BaseModel):
    account_code: str = Field(min_length=2, max_length=20)
    debit: int = Field(default=0, ge=0)
    credit: int = Field(default=0, ge=0)


class JournalIn(BaseModel):
    description: str | None = Field(default=None, max_length=300)
    source_type: str | None = Field(default=None, max_length=30)
    source_id: uuid.UUID | None = None
    lines: list[JournalLineIn]


class SettlementIn(BaseModel):
    consultant_id: uuid.UUID
    period_from: datetime
    period_to: datetime
    gross_amount: int = Field(gt=0)
    share_percent: float = Field(default=0, ge=0, le=100)


@router.post("/accounts", status_code=201)
def create_account(
    body: AccountIn,
    user: User = Depends(require_permission("accounting.manage")),
    db: Session = Depends(get_db),
):
    exists = db.execute(select(Account).where(Account.code == body.code)).scalar_one_or_none()
    if exists is not None:
        return error_response("ACCOUNT_EXISTS", "کد حساب قبلاً ثبت شده است", 409)
    acc = Account(code=body.code, name=body.name, kind=body.kind)
    db.add(acc)
    db.commit()
    return envelope(data={"id": str(acc.id), "code": acc.code, "name": acc.name})


@router.get("/accounts")
def list_accounts(
    user: User = Depends(require_permission("accounting.manage")),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Account).order_by(Account.code)).scalars().all()
    return envelope(
        data=[
            {
                "id": str(a.id),
                "code": a.code,
                "name": a.name,
                "kind": a.kind,
                "balance": account_balance(db, a.id),
            }
            for a in rows
        ]
    )


@router.post("/journal-entries", status_code=201)
def create_journal_entry(
    body: JournalIn,
    user: User = Depends(require_permission("accounting.manage")),
    db: Session = Depends(get_db),
):
    try:
        entry = post_journal(
            db,
            lines=[ln.model_dump() for ln in body.lines],
            description=body.description,
            source_type=body.source_type,
            source_id=body.source_id,
            posted_by=user.id,
        )
    except ValueError:
        return error_response("JOURNAL_INVALID", "سند حسابداری نامعتبر است", 422)
    db.commit()
    return envelope(data=journal_data(db, entry))


@router.get("/journal-entries")
def list_journal_entries(
    user: User = Depends(require_permission("accounting.manage")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(JournalEntry).order_by(JournalEntry.posted_at.desc()).limit(100)
    ).scalars().all()
    return envelope(data=[journal_data(db, e) for e in rows])


@router.post("/settlements", status_code=201)
def create_settlement(
    body: SettlementIn,
    user: User = Depends(require_permission("accounting.manage")),
    db: Session = Depends(get_db),
):
    if body.period_to <= body.period_from:
        return error_response("SETTLEMENT_WINDOW_INVALID", "بازه تسویه نامعتبر است", 422)
    consultant = db.get(Consultant, body.consultant_id)
    if consultant is None:
        return error_response("CONSULTANT_NOT_FOUND", "مشاور یافت نشد", 404)
    net = round(body.gross_amount * (100 - body.share_percent) / 100)
    st = Settlement(
        consultant_id=body.consultant_id,
        period_from=body.period_from,
        period_to=body.period_to,
        gross_amount=body.gross_amount,
        share_percent=body.share_percent,
        net_amount=net,
        created_by=user.id,
    )
    db.add(st)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="settlement.create",
        outcome="allowed",
        resource_type="settlement",
        resource_id=st.id,
        detail={"net": net},
    )
    return envelope(data=_settlement_data(st))


def _settlement_data(st: Settlement) -> dict:
    return {
        "id": str(st.id),
        "consultant_id": str(st.consultant_id),
        "period_from": st.period_from.isoformat(),
        "period_to": st.period_to.isoformat(),
        "gross_amount": int(st.gross_amount),
        "share_percent": float(st.share_percent),
        "net_amount": int(st.net_amount),
        "status": st.status,
        "paid_at": st.paid_at.isoformat() if st.paid_at else None,
    }


@router.post("/settlements/{settlement_id}/advance")
def advance_settlement(
    settlement_id: uuid.UUID,
    user: User = Depends(require_permission("accounting.manage")),
    db: Session = Depends(get_db),
):
    st = db.get(Settlement, settlement_id)
    if st is None:
        return error_response("SETTLEMENT_NOT_FOUND", "تسویه یافت نشد", 404)
    nxt = SETTLEMENT_TRANSITIONS.get(st.status)
    if nxt is None:
        return error_response("INVALID_SETTLEMENT_TRANSITION", "انتقال وضعیت مجاز نیست", 409)
    st.status = nxt
    if nxt == "paid":
        st.paid_at = datetime.now(UTC)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action=f"settlement.{nxt}",
        outcome="allowed",
        resource_type="settlement",
        resource_id=st.id,
    )
    return envelope(data=_settlement_data(st))
