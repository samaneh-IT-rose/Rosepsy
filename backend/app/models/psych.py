"""B37 — Psychology tests and interpretation (Release 4).

Spec rules (docs/requirements.md §17, B37):
- ورود و رضایت پیش از اجرا: login + a valid consent (kind per test) is required
  before an attempt can be answered.
- نسخه پاسخ‌ها ثابت: an attempt is bound to one immutable test version; scoring
  uses the option scores snapshotted in that version.
- انتشار قواعد تفسیر تنها پس از تأیید علمی: a version and its interpretation
  rules must be approved by the scientific reviewer (ناظر علمی) before publish.
- نتیجه فرد دیگر دیده نشود: results are owner-only; scientific reviewer access
  is permitted and every sensitive read is logged (audit.access_events).
- تفسیر قابل ردیابی به نسخه و قاعده مصوب: the scored attempt stores the rule id
  and a snapshot of the approved interpretation text.

State machine (spec §6): psych_attempts:
started → consented → in_progress → scored → reviewed ‖ abandoned
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class PsychTest(Base):
    """Test catalog entry (کاتالوگ تست): هدف، جمعیت هدف، محدودیت سنی، رضایت."""

    __tablename__ = "psych_tests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','published','archived')",
            name="ck_psych_tests_status",
        ),
        CheckConstraint(
            "(age_min IS NULL OR age_min >= 0) AND (age_max IS NULL OR age_max <= 120)",
            name="ck_psych_tests_age_range",
        ),
        {"schema": "psych"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str | None] = mapped_column(String(1000))  # هدف
    target_population: Mapped[str | None] = mapped_column(String(300))  # جمعیت هدف
    age_min: Mapped[int | None] = mapped_column(Integer)  # محدودیت سنی
    age_max: Mapped[int | None] = mapped_column(Integer)
    consent_kind: Mapped[str] = mapped_column(String(40), default="psych_test")
    scientific_doc: Mapped[str | None] = mapped_column(String(300))  # مستند علمی
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PsychTestVersion(Base):
    """نسخه سؤال + مقیاس + قاعده نمره. Publish only after scientific approval."""

    __tablename__ = "psych_test_versions"
    __table_args__ = (
        UniqueConstraint("test_id", "version", name="ux_psych_versions_test_ver"),
        CheckConstraint(
            "status IN ('draft','approved','published','archived')",
            name="ck_psych_versions_status",
        ),
        CheckConstraint("scoring_method IN ('sum')", name="ck_psych_versions_scoring"),
        {"schema": "psych"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_tests.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    scale_label: Mapped[str] = mapped_column(String(120))  # مقیاس (مثلاً لیکرت ۴درجه‌ای)
    scoring_method: Mapped[str] = mapped_column(String(12), default="sum")  # قاعده نمره
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PsychQuestion(Base):
    """Question of one version; options carry fixed scores (نسخه پاسخ ثابت)."""

    __tablename__ = "psych_questions"
    __table_args__ = {"schema": "psych"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_test_versions.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(1000))
    options: Mapped[list] = mapped_column(JSONB)  # [{label: str, score: int}, ...]
    weight: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=1)


class PsychInterpretationRule(Base):
    """قاعده تفسیر: band of raw scores → title + guidance.
    Requires scientific approval before the version can be published."""

    __tablename__ = "psych_interpretation_rules"
    __table_args__ = (
        CheckConstraint("min_score <= max_score", name="ck_psych_rules_band"),
        CheckConstraint("status IN ('draft','approved')", name="ck_psych_rules_status"),
        {"schema": "psych"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_test_versions.id", ondelete="CASCADE"), index=True
    )
    min_score: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    guidance: Mapped[str] = mapped_column(String(2000))  # متن تفسیر مصوب
    status: Mapped[str] = mapped_column(String(10), default="draft")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PsychAttempt(Base):
    """State machine: started → consented → in_progress → scored → reviewed ‖ abandoned."""

    __tablename__ = "psych_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','consented','in_progress','scored','reviewed','abandoned')",
            name="ck_psych_attempts_status",
        ),
        {"schema": "psych"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_tests.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_test_versions.id", ondelete="RESTRICT"), index=True
    )  # نسخه ثابت در شروع
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.consents.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(12), default="started", index=True)
    raw_score: Mapped[int | None] = mapped_column(Integer)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("psych.psych_interpretation_rules.id", ondelete="RESTRICT")
    )
    interpretation_title: Mapped[str | None] = mapped_column(String(200))
    interpretation_text: Mapped[str | None] = mapped_column(String(2000))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(1000))


class PsychAnswer(Base):
    """One stored answer per question; option_score frozen from the version."""

    __tablename__ = "psych_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_psych_answers_attempt_q"),
        {"schema": "psych"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("psych.psych_questions.id", ondelete="RESTRICT")
    )
    option_index: Mapped[int] = mapped_column(Integer)
    option_score: Mapped[int] = mapped_column(Integer, default=0)


def user_age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
