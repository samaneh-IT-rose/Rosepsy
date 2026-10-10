import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class ConsentVersion(Base):
    """Immutable consent text template (B41). Protected by a DB trigger:
    UPDATE/DELETE raise - see migration 0011. Active version = highest number."""

    __tablename__ = "consent_versions"
    __table_args__ = (
        UniqueConstraint("kind", "version", name="ux_core_consent_versions_kind_ver"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title_fa: Mapped[str] = mapped_column(String(150))
    text_fa: Mapped[str] = mapped_column(String(5000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Consent(Base):
    """A user's grant of one consent kind. State machine per spec s.09a:
    granted -> revoked (revocation keeps history; future grants allowed)."""

    __tablename__ = "consents"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.consent_versions.id", ondelete="RESTRICT")
    )
    channel: Mapped[str] = mapped_column(String(20), default="web")
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
