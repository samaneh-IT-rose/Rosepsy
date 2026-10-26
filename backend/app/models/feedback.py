"""B23 — Feedback: surveys, support tickets and ticket messages (core schema).

Rule from the spec: a complaint must be followable WITHOUT exposing the
clinical record content to the support staff - these tables therefore carry
no clinical references at all.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class SurveyResponse(Base):
    """Post-service survey (B23): NPS-style score 0..10 with optional comment."""

    __tablename__ = "survey_responses"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 10", name="ck_core_surveys_score_range"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("booking.appointments.id", ondelete="SET NULL"), unique=True
    )
    score: Mapped[int] = mapped_column()
    comment: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SupportTicket(Base):
    """Support ticket (B23): open -> in_progress -> resolved | closed."""

    __tablename__ = "support_tickets"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(4000))
    status: Mapped[str] = mapped_column(String(14), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketMessage(Base):
    """Conversation line on a ticket (B23)."""

    __tablename__ = "ticket_messages"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.support_tickets.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(String(4000))
    is_staff: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
