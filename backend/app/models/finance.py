import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Uuid, func
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
