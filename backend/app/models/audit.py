import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class AuditLog(Base):
    """Access/permission audit trail (B04 + spec s.12).

    Deliberately has NO FK to core.users so audit rows survive any future
    user removal (data-retention policy).
    """

    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    outcome: Mapped[str] = mapped_column(String(16))  # allowed | denied
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    detail: Mapped[dict | None] = mapped_column(JSONB)


class AccessEvent(Base):
    """Structured data-access event (B41): who touched whose resource.
    B13 (clinical records) writes here on every sensitive read."""

    __tablename__ = "access_events"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    allowed: Mapped[bool] = mapped_column(Boolean)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    detail: Mapped[dict | None] = mapped_column(JSONB)
