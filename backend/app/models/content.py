"""B33 — CMS: articles/news/podcasts/videos with revisions (content schema).

State machine per spec s.09a: draft -> in_review -> published | rejected,
published -> archived. Drafts are never public; every edit of a published
item keeps the previous version as an immutable revision row.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class Content(Base):
    __tablename__ = "contents"
    __table_args__ = (
        CheckConstraint(
            "type IN ('article','news','podcast','video')",
            name="ck_content_contents_type",
        ),
        {"schema": "content"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    type: Mapped[str] = mapped_column(String(12), index=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(String(20000))
    media_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.files.id", ondelete="SET NULL")
    )
    source: Mapped[str | None] = mapped_column(String(200))
    seo_title: Mapped[str | None] = mapped_column(String(200))
    seo_description: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContentRevision(Base):
    """Immutable snapshot of a content state (B33: تاریخچه تغییر کار کند)."""

    __tablename__ = "content_revisions"
    __table_args__ = {"schema": "content"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    content_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content.contents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column()
    snapshot: Mapped[dict] = mapped_column(JSONB)
    editor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContentTopic(Base):
    __tablename__ = "content_topics"
    __table_args__ = (
        UniqueConstraint("content_id", "topic_id", name="uq_content_topics_pair"),
        {"schema": "content"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    content_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content.contents.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.topics.id", ondelete="CASCADE"), index=True
    )
