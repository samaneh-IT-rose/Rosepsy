"""Accounting service (B22): balanced journals tied to financial events.

Rules (spec): every journal entry must balance (sum debit == sum credit),
be traceable to its financial event (source_type + source_id unique), and
never be posted twice for the same event. Standard accounts are created
on demand so the seed stays optional.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.finance import Account, JournalEntry, JournalLine
from app.services.authz import write_audit

STANDARD_ACCOUNTS: list[tuple[str, str, str]] = [
    ("1001", "موجودی نقد و بانک", "asset"),
    ("2100", "بدهی کیف پول کاربران", "liability"),
    ("4000", "درآمد خدمات مشاوره", "revenue"),
    ("4001", "درآمد فروش دوره", "revenue"),
]


def get_or_create_account(db: Session, code: str) -> Account:
    acc = db.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
    if acc is not None:
        return acc
    for c, name, kind in STANDARD_ACCOUNTS:
        if c == code:
            acc = Account(code=c, name=name, kind=kind)
            db.add(acc)
            db.flush()
            return acc
    raise HTTPException(status_code=422, detail="ACCOUNT_CODE_UNKNOWN")


def next_entry_no(db: Session) -> str:
    db.execute(text("CREATE SEQUENCE IF NOT EXISTS finance.journal_entry_seq START 1"))
    seq = db.execute(text("SELECT nextval('finance.journal_entry_seq')")).scalar_one()
    return f"JE-{seq:06d}"


def post_journal(
    db: Session,
    *,
    lines: list[dict],
    description: str | None = None,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    posted_by: uuid.UUID | None = None,
) -> JournalEntry:
    """lines: [{'account_code': '1001', 'debit': 1000} | {'account_code': '4000', 'credit': 1000}]

    Idempotent per (source_type, source_id); raises 422 on unbalanced input.
    """
    if source_type and source_id:
        existing = db.execute(
            select(JournalEntry).where(
                JournalEntry.source_type == source_type, JournalEntry.source_id == source_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    if len(lines) < 2:
        raise HTTPException(status_code=422, detail="JOURNAL_NEEDS_TWO_LINES")

    total_debit = 0
    total_credit = 0
    resolved: list[tuple[Account, int, int]] = []
    for ln in lines:
        amount_d = int(ln.get("debit") or 0)
        amount_c = int(ln.get("credit") or 0)
        if (amount_d > 0) == (amount_c > 0):
            raise HTTPException(status_code=422, detail="JOURNAL_LINE_ONE_SIDE")
        account = get_or_create_account(db, str(ln.get("account_code", "")))
        resolved.append((account, amount_d, amount_c))
        total_debit += amount_d
        total_credit += amount_c

    if total_debit != total_credit or total_debit <= 0:
        raise HTTPException(status_code=422, detail="JOURNAL_NOT_BALANCED")

    entry = JournalEntry(
        entry_no=next_entry_no(db),
        description=(description or "")[:300] or None,
        source_type=source_type,
        source_id=source_id,
        posted_by=posted_by,
    )
    db.add(entry)
    db.flush()
    for account, amount_d, amount_c in resolved:
        db.add(
            JournalLine(
                entry_id=entry.id, account_id=account.id, debit=amount_d, credit=amount_c
            )
        )
    db.flush()
    write_audit(
        db,
        actor_user_id=posted_by,
        action="journal.post",
        outcome="allowed",
        resource_type="journal_entry",
        resource_id=entry.id,
        detail={"entry_no": entry.entry_no, "total": total_debit},
    )
    return entry


def post_order_paid_journal(db: Session, order) -> JournalEntry | None:
    """Auto-post the revenue journal when an order is paid (cash vs wallet)."""
    try:
        if order.order_type == "wallet_topup":
            # wallet topup: cash in, wallet liability up
            return post_journal(
                db,
                lines=[
                    {"account_code": "1001", "debit": int(order.amount)},
                    {"account_code": "2100", "credit": int(order.amount)},
                ],
                description="شارژ کیف پول",
                source_type="order_topup",
                source_id=order.id,
            )
        if order.appointment_id is not None:
            return post_journal(
                db,
                lines=[
                    {"account_code": "1001", "debit": int(order.amount)},
                    {"account_code": "4000", "credit": int(order.amount)},
                ],
                description="درآمد خدمات مشاوره",
                source_type="order",
                source_id=order.id,
            )
        return None
    except HTTPException:
        return None


def journal_data(db: Session, entry: JournalEntry) -> dict:
    from app.models.finance import Account as _A

    lines = db.execute(
        select(JournalLine, _A.code, _A.name)
        .join(_A, _A.id == JournalLine.account_id)
        .where(JournalLine.entry_id == entry.id)
    ).all()
    return {
        "id": str(entry.id),
        "entry_no": entry.entry_no,
        "description": entry.description,
        "source_type": entry.source_type,
        "source_id": str(entry.source_id) if entry.source_id else None,
        "posted_at": entry.posted_at.isoformat(),
        "lines": [
            {
                "account_code": code,
                "account_name": name,
                "debit": int(line.debit),
                "credit": int(line.credit),
            }
            for line, code, name in lines
        ],
        "total_debit": sum(int(line.debit) for line, _, _ in lines),
        "total_credit": sum(int(line.credit) for line, _, _ in lines),
    }


def account_balance(db: Session, account_id: uuid.UUID) -> int:
    debit = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0)).where(
            JournalLine.account_id == account_id
        )
    ).scalar_one()
    credit = db.execute(
        select(func.coalesce(func.sum(JournalLine.credit), 0)).where(
            JournalLine.account_id == account_id
        )
    ).scalar_one()
    return int(debit) - int(credit)
