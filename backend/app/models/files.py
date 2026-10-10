import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class File(Base):
    """Secure file record (B39). State machine per spec s.09a:
    uploaded -> scanning -> clean | quarantined | deleted.
    Bytes live in MinIO; the DB holds metadata only (spec s.03)."""

    __tablename__ = "files"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    context: Mapped[str] = mapped_column(String(32), default="general")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    checksum: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
