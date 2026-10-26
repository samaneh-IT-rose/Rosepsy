"""Wallet service (B18): ledger-based balance, row-locked debits, no double-spend.

Rules from the spec:
- balance must always equal the sum of entries (credit positive, debit negative)
- spending more than the balance is impossible (row lock + explicit check)
- every mutation writes an immutable ledger entry (wallet_entries)
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import Wallet, WalletEntry
from app.services.authz import write_audit


def get_or_create_wallet(db: Session, user_id: uuid.UUID) -> Wallet:
    wallet = db.execute(
        select(Wallet).where(Wallet.user_id == user_id)
    ).scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(user_id=user_id)
        db.add(wallet)
        db.flush()
    return wallet


def wallet_balance(db: Session, wallet_id: uuid.UUID) -> int:
    """Authoritative balance = last entry's balance_after (0 when empty)."""
    last = db.execute(
        select(WalletEntry)
        .where(WalletEntry.wallet_id == wallet_id)
        .order_by(WalletEntry.created_at.desc(), WalletEntry.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return int(last.balance_after) if last is not None else 0


def _add_entry(
    db: Session,
    *,
    wallet_id: uuid.UUID,
    direction: str,
    amount: int,
    entry_type: str,
    balance_after: int,
    order_id: uuid.UUID | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    created_by: uuid.UUID | None = None,
) -> WalletEntry:
    entry = WalletEntry(
        wallet_id=wallet_id,
        direction=direction,
        amount=amount,
        balance_after=balance_after,
        entry_type=entry_type,
        order_id=order_id,
        note=(note or "")[:300] or None,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )
    db.add(entry)
    db.flush()
    return entry


def credit_wallet(
    db: Session,
    *,
    user_id: uuid.UUID,
    amount: int,
    entry_type: str,
    order_id: uuid.UUID | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> WalletEntry:
    """Credit (topup / refund / adjustment). Idempotent when a key is given."""
    if amount <= 0:
        raise HTTPException(status_code=422, detail="WALLET_AMOUNT_INVALID")

    if idempotency_key:
        existing = db.execute(
            select(WalletEntry)
            .join(Wallet, Wallet.id == WalletEntry.wallet_id)
            .where(Wallet.user_id == user_id, WalletEntry.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    wallet = get_or_create_wallet(db, user_id)
    locked = db.execute(
        select(Wallet).where(Wallet.id == wallet.id).with_for_update()
    ).scalar_one()
    balance = wallet_balance(db, locked.id)
    entry = _add_entry(
        db,
        wallet_id=locked.id,
        direction="credit",
        amount=amount,
        entry_type=entry_type,
        balance_after=balance + amount,
        order_id=order_id,
        note=note,
        idempotency_key=idempotency_key,
        created_by=actor_user_id,
    )
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action=f"wallet.{entry_type}",
        outcome="allowed",
        resource_type="wallet_entry",
        resource_id=entry.id,
        detail={"user_id": str(user_id), "amount": amount},
    )
    return entry


def debit_wallet(
    db: Session,
    *,
    user_id: uuid.UUID,
    amount: int,
    entry_type: str,
    order_id: uuid.UUID | None = None,
    note: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> WalletEntry:
    """Debit (payment). Raises 409 WALLET_INSUFFICIENT_FUNDS when balance is short."""
    if amount <= 0:
        raise HTTPException(status_code=422, detail="WALLET_AMOUNT_INVALID")

    wallet = get_or_create_wallet(db, user_id)
    locked = db.execute(
        select(Wallet).where(Wallet.id == wallet.id).with_for_update()
    ).scalar_one()
    balance = wallet_balance(db, locked.id)
    if balance < amount:
        raise HTTPException(status_code=409, detail="WALLET_INSUFFICIENT_FUNDS")
    entry = _add_entry(
        db,
        wallet_id=locked.id,
        direction="debit",
        amount=amount,
        entry_type=entry_type,
        balance_after=balance - amount,
        order_id=order_id,
        note=note,
        created_by=actor_user_id,
    )
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action=f"wallet.{entry_type}",
        outcome="allowed",
        resource_type="wallet_entry",
        resource_id=entry.id,
        detail={"user_id": str(user_id), "amount": amount},
    )
    return entry


def entry_data(entry: WalletEntry) -> dict:
    return {
        "id": str(entry.id),
        "wallet_id": str(entry.wallet_id),
        "direction": entry.direction,
        "amount": int(entry.amount),
        "balance_after": int(entry.balance_after),
        "entry_type": entry.entry_type,
        "order_id": str(entry.order_id) if entry.order_id else None,
        "note": entry.note,
        "created_at": entry.created_at.isoformat(),
    }


def wallet_data(db: Session, wallet: Wallet) -> dict:
    return {
        "id": str(wallet.id),
        "user_id": str(wallet.user_id),
        "currency": wallet.currency,
        "balance": wallet_balance(db, wallet.id),
        "is_active": wallet.is_active,
    }
