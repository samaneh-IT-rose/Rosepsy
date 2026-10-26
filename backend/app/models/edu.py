"""B34+B35+B36 — Education: courses, lessons, enrollments, exams, certificates.

Rules from the spec:
- free course has price 0; paid course has a positive price (DB check)
- a course can be published only with at least one valid lesson
- published lesson edits keep the previous version (lesson_versions)
- paid access only after server-side payment confirmation; a duplicate
  enrollment request never duplicates access (B35)
- exam scoring happens server-side only; attempt cap enforced server-side;
  a certificate is issued exactly once per passing attempt (B36)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(
            "(is_free AND price = 0) OR ((NOT is_free) AND price > 0)",
            name="ck_edu_courses_price_consistent",
        ),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.topics.id", ondelete="SET NULL")
    )
    summary: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(10000))
    instructor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    instructor_name: Mapped[str | None] = mapped_column(String(120))
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    price: Mapped[int] = mapped_column(Numeric(14, 0), default=0)
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseModule(Base):
    __tablename__ = "course_modules"
    __table_args__ = {"schema": "edu"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.courses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=1)


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint(
            "lesson_type IN ('video','pdf')", name="ck_edu_lessons_type"
        ),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    module_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.course_modules.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    lesson_type: Mapped[str] = mapped_column(String(8), default="video")
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.files.id", ondelete="SET NULL")
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=1)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LessonVersion(Base):
    """Snapshot kept when a published lesson is edited (B34: نسخه درس حفظ شود)."""

    __tablename__ = "lesson_versions"
    __table_args__ = {"schema": "edu"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.lessons.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column()
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_edu_progress_user_lesson"),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.lessons.id", ondelete="CASCADE"), index=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseEnrollment(Base):
    """State machine per spec: pending_payment -> active -> completed | expired | revoked."""

    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_edu_enroll_user_course"),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.courses.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending_payment", index=True)
    source: Mapped[str] = mapped_column(String(12), default="free")  # free|purchase|admin
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessGrant(Base):
    """Effective access to a course (B35): source-traceable, revocable, expirable."""

    __tablename__ = "access_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_edu_grants_user_course"),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.courses.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(12))  # free|purchase|admin|gift
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("finance.orders.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CourseExam(Base):
    __tablename__ = "course_exams"
    __table_args__ = (
        CheckConstraint(
            "pass_score >= 0 AND pass_score <= 100", name="ck_edu_exams_pass_score"
        ),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.courses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    pass_score: Mapped[int] = mapped_column(Integer, default=60)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=20)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = {"schema": "edu"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.course_exams.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(2000))
    options: Mapped[list] = mapped_column(JSONB)  # list of strings
    correct_index: Mapped[int] = mapped_column(Integer)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=1)


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    __table_args__ = {"schema": "edu"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.course_exams.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(12), default="in_progress", index=True)
    score: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExamAnswer(Base):
    __tablename__ = "exam_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_edu_answers_attempt_question"),
        {"schema": "edu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.exam_attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.exam_questions.id", ondelete="CASCADE")
    )
    selected_index: Mapped[int] = mapped_column(Integer)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = {"schema": "edu"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.courses.id", ondelete="CASCADE"), index=True
    )
    exam_attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("edu.exam_attempts.id", ondelete="RESTRICT"), unique=True
    )
    certificate_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    verification_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
