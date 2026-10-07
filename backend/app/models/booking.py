import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class SlotClaim(Base):
    """Temporary hold on a slot (B09). status: held|consumed|expired|released."""

    __tablename__ = "slot_claims"
    __table_args__ = {"schema": "booking"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.consultants.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.services.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="held", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Appointment(Base):
    """Final appointment (B09). State machine per spec s.09a:
    pending_payment -> confirmed -> in_progress -> completed | cancelled | no_show
    """

    __tablename__ = "appointments"
    __table_args__ = {"schema": "booking"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.consultants.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.services.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    hold_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("booking.slot_claims.id", ondelete="SET NULL"), unique=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending_payment", index=True)
    price_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
