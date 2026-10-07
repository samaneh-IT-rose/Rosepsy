import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class WeeklyRule(Base):
    """Consultant weekly working window: weekday + local wall-clock times."""

    __tablename__ = "availability_weekly_rules"
    __table_args__ = (
        UniqueConstraint(
            "consultant_id", "weekday", "start_time", "end_time",
            name="ux_booking_weekly_rules_full",
        ),
        {"schema": "booking"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.consultants.id", ondelete="CASCADE"), index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.branches.id", ondelete="SET NULL")
    )
    weekday: Mapped[int] = mapped_column(Integer)  # ISO: 0=Mon .. 6=Sun
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AvailabilityException(Base):
    """Blocking window (leave / one-off block) in absolute UTC time."""

    __tablename__ = "availability_exceptions"
    __table_args__ = {"schema": "booking"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.consultants.id", ondelete="CASCADE"), index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
