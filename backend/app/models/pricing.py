import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class Tariff(Base):
    """Price container per service (optionally per branch); actual prices live in versions."""

    __tablename__ = "tariffs"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    service_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.services.id", ondelete="CASCADE"), index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.branches.id", ondelete="CASCADE"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TariffVersion(Base):
    """One price over one validity half-open range [valid_from, valid_to)."""

    __tablename__ = "tariff_versions"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_core_tariff_versions_range",
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tariff_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.tariffs.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(Numeric(14, 0))
    currency: Mapped[str] = mapped_column(String(3), default="IRR")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
