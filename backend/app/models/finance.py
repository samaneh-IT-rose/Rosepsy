import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class Order(Base):
    """Payment order (B10). State machine per spec: awaiting_payment -> paid | failed."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_orders_amount_positive"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("booking.appointments.id", ondelete="SET NULL")
    )
    order_type: Mapped[str] = mapped_column(String(20), default="appointment")
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    currency: Mapped[str] = mapped_column(String(3), default="IRR")
    status: Mapped[str] = mapped_column(String(20), default="awaiting_payment", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    price_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    discount_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("finance.discounts.id", ondelete="SET NULL")
    )
    discount_amount: Mapped[int] = mapped_column(Numeric(14, 0), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "finance"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="CASCADE"), index=True
    )
    gateway: Mapped[str] = mapped_column(String(20), default="mock")
    gateway_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    currency: Mapped[str] = mapped_column(String(3), default="IRR")
    status: Mapped[str] = mapped_column(String(16), default="initiated", index=True)
    raw_callback: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(Base):
    """One invoice per paid order; immutable amount from the order snapshot (B11)."""

    __tablename__ = "invoices"
    __table_args__ = {"schema": "finance"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="CASCADE"), unique=True
    )
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    currency: Mapped[str] = mapped_column(String(3), default="IRR")
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __table_args__ = {"schema": "finance"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.invoices.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_amount: Mapped[int] = mapped_column(Numeric(14, 0))
    total: Mapped[int] = mapped_column(Numeric(14, 0))


# ────────────────────────────── B18 · Wallet ──────────────────────────────


class Wallet(Base):
    """Per-user wallet (B18). Balance is derived from entries, never stored loose:
    the last entry's balance_after is the authoritative balance."""

    __tablename__ = "wallets"
    __table_args__ = {"schema": "finance"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), unique=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="IRR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WalletEntry(Base):
    """Immutable ledger line (B18). amount is always positive; direction sets the sign.
    Acceptance: balance consistency with entries sum; no double-spend."""

    __tablename__ = "wallet_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_wallet_entries_amount_positive"),
        CheckConstraint(
            "direction IN ('credit','debit')", name="ck_finance_wallet_entries_direction"
        ),
        Index(
            "ux_finance_wallet_entries_wallet_idem",
            "wallet_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.wallets.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(6))
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    balance_after: Mapped[int] = mapped_column(Numeric(14, 0))
    entry_type: Mapped[str] = mapped_column(String(20))  # topup | payment | refund | adjustment
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(300))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ────────────────────────────── B19 · Discounts ──────────────────────────────


class Discount(Base):
    """Discount code (B19): percent or fixed, with hard caps enforced server-side."""

    __tablename__ = "discounts"
    __table_args__ = (
        CheckConstraint("value > 0", name="ck_finance_discounts_value_positive"),
        CheckConstraint("kind IN ('percent','fixed')", name="ck_finance_discounts_kind"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(10), default="fixed")
    value: Mapped[int] = mapped_column(Numeric(14, 0))
    min_order_amount: Mapped[int] = mapped_column(Numeric(14, 0), default=0)
    max_redemptions_total: Mapped[int | None] = mapped_column(Integer)
    max_redemptions_per_user: Mapped[int | None] = mapped_column(Integer)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DiscountRedemption(Base):
    """One redemption per order (B19). Created atomically with the order while
    holding a row lock on the discount, so concurrent redemptions cannot
    exceed max_redemptions_total (spec acceptance)."""

    __tablename__ = "discount_redemptions"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_finance_redemptions_order"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    discount_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.discounts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="CASCADE")
    )
    amount_applied: Mapped[int] = mapped_column(Numeric(14, 0))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ────────────────────────────── B20 · Refunds ──────────────────────────────


class RefundRequest(Base):
    """Refund request (B20). State machine per spec s.09a:
    submitted -> reviewing -> approved -> executed | rejected."""

    __tablename__ = "refund_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_refund_requests_amount_positive"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="submitted", index=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    decision_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Refund(Base):
    """Executed refund (B20): unique per request; money returns to the wallet (B18)."""

    __tablename__ = "refunds"
    __table_args__ = {"schema": "finance"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    refund_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("finance.refund_requests.id", ondelete="CASCADE"), unique=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("finance.payments.id", ondelete="SET NULL")
    )
    wallet_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("finance.wallet_entries.id", ondelete="SET NULL")
    )
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    executed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
