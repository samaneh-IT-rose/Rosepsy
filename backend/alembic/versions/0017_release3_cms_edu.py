"""Release 3 · B33-B36: CMS (content) + courses/enrollments/exams/certificates (edu)

Revision ID: 0017
Revises: 0016
Create Date: 2025-01-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS content")
    op.execute("CREATE SCHEMA IF NOT EXISTS edu")

    # ── B33 CMS ──
    op.create_table(
        "contents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("body", sa.String(20000), nullable=True),
        sa.Column("media_file_id", UUID, nullable=True),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("seo_title", sa.String(200), nullable=True),
        sa.Column("seo_description", sa.String(300), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("author_user_id", UUID, nullable=True),
        sa.Column("published_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "type IN ('article','news','podcast','video')", name="ck_content_contents_type"
        ),
        sa.ForeignKeyConstraint(["media_file_id"], ["core.files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_user_id"], ["core.users.id"], ondelete="SET NULL"),
        schema="content",
    )
    op.create_index("ux_content_contents_slug", "contents", ["slug"], unique=True, schema="content")
    op.create_index("ix_content_contents_type", "contents", ["type"], schema="content")
    op.create_index("ix_content_contents_status", "contents", ["status"], schema="content")

    op.create_table(
        "content_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("content_id", UUID, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("editor_user_id", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content.contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["editor_user_id"], ["core.users.id"], ondelete="SET NULL"),
        schema="content",
    )
    op.create_index(
        "ix_content_revisions_content", "content_revisions", ["content_id"], schema="content"
    )

    op.create_table(
        "content_topics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("content_id", UUID, nullable=False),
        sa.Column("topic_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content.contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["core.topics.id"], ondelete="CASCADE"),
        schema="content",
    )
    op.create_index(
        "uq_content_topics_pair", "content_topics", ["content_id", "topic_id"],
        unique=True, schema="content",
    )
    op.create_index("ix_content_topics_topic", "content_topics", ["topic_id"], schema="content")

    # ── B34 courses ──
    op.create_table(
        "courses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("topic_id", UUID, nullable=True),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("description", sa.String(10000), nullable=True),
        sa.Column("instructor_user_id", UUID, nullable=True),
        sa.Column("instructor_name", sa.String(120), nullable=True),
        sa.Column("is_free", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("price", sa.Numeric(14, 0), nullable=False, server_default="0"),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("published_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "(is_free AND price = 0) OR ((NOT is_free) AND price > 0)",
            name="ck_edu_courses_price_consistent",
        ),
        sa.ForeignKeyConstraint(["topic_id"], ["core.topics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instructor_user_id"], ["core.users.id"], ondelete="SET NULL"),
        schema="edu",
    )
    op.create_index("ux_edu_courses_slug", "courses", ["slug"], unique=True, schema="edu")
    op.create_index("ix_edu_courses_status", "courses", ["status"], schema="edu")

    op.create_table(
        "course_modules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["course_id"], ["edu.courses.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index(
        "ix_edu_modules_course", "course_modules", ["course_id"], schema="edu"
    )

    op.create_table(
        "lessons",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("module_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("lesson_type", sa.String(8), nullable=False, server_default="video"),
        sa.Column("file_id", UUID, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("position", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_preview", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("lesson_type IN ('video','pdf')", name="ck_edu_lessons_type"),
        sa.ForeignKeyConstraint(["module_id"], ["edu.course_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["core.files.id"], ondelete="SET NULL"),
        schema="edu",
    )
    op.create_index("ix_edu_lessons_module", "lessons", ["module_id"], schema="edu")

    op.create_table(
        "lesson_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("lesson_id", UUID, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["edu.lessons.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index(
        "ix_edu_lesson_versions_lesson", "lesson_versions", ["lesson_id"], schema="edu"
    )

    op.create_table(
        "lesson_progress",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("lesson_id", UUID, nullable=False),
        sa.Column("completed_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["edu.lessons.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index(
        "uq_edu_progress_user_lesson", "lesson_progress", ["user_id", "lesson_id"],
        unique=True, schema="edu",
    )

    # ── B35 enrollments ──
    op.create_table(
        "course_enrollments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending_payment"),
        sa.Column("source", sa.String(12), nullable=False, server_default="free"),
        sa.Column("order_id", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("activated_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["edu.courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="SET NULL"),
        schema="edu",
    )
    op.create_index(
        "uq_edu_enroll_user_course", "course_enrollments", ["user_id", "course_id"],
        unique=True, schema="edu",
    )
    op.create_index(
        "ix_edu_enroll_status", "course_enrollments", ["status"], schema="edu"
    )

    op.create_table(
        "access_grants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("order_id", UUID, nullable=True),
        sa.Column("granted_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("expires_at", TSTZ, nullable=True),
        sa.Column("revoked_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["edu.courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="SET NULL"),
        schema="edu",
    )
    op.create_index(
        "uq_edu_grants_user_course", "access_grants", ["user_id", "course_id"],
        unique=True, schema="edu",
    )

    # ── B36 exams & certificates ──
    op.create_table(
        "course_exams",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("pass_score", sa.Integer, nullable=False, server_default="60"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="20"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("pass_score >= 0 AND pass_score <= 100", name="ck_edu_exams_pass_score"),
        sa.ForeignKeyConstraint(["course_id"], ["edu.courses.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index("ix_edu_exams_course", "course_exams", ["course_id"], schema="edu")

    op.create_table(
        "exam_questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("exam_id", UUID, nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("correct_index", sa.Integer, nullable=False),
        sa.Column("weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("position", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["exam_id"], ["edu.course_exams.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index("ix_edu_questions_exam", "exam_questions", ["exam_id"], schema="edu")

    op.create_table(
        "exam_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("exam_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("started_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("submitted_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["edu.course_exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index("ix_edu_attempts_exam", "exam_attempts", ["exam_id"], schema="edu")
    op.create_index("ix_edu_attempts_user", "exam_attempts", ["user_id"], schema="edu")
    op.create_index("ix_edu_attempts_status", "exam_attempts", ["status"], schema="edu")

    op.create_table(
        "exam_answers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("question_id", UUID, nullable=False),
        sa.Column("selected_index", sa.Integer, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["attempt_id"], ["edu.exam_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["edu.exam_questions.id"], ondelete="CASCADE"),
        schema="edu",
    )
    op.create_index(
        "uq_edu_answers_attempt_question", "exam_answers", ["attempt_id", "question_id"],
        unique=True, schema="edu",
    )

    op.create_table(
        "certificates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("exam_attempt_id", UUID, nullable=False),
        sa.Column("certificate_number", sa.String(30), nullable=False),
        sa.Column("verification_code", sa.String(16), nullable=False),
        sa.Column("issued_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["edu.courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["exam_attempt_id"], ["edu.exam_attempts.id"], ondelete="RESTRICT"
        ),
        schema="edu",
    )
    op.create_index(
        "ux_edu_certificates_number", "certificates", ["certificate_number"],
        unique=True, schema="edu",
    )
    op.create_index(
        "ux_edu_certificates_code", "certificates", ["verification_code"],
        unique=True, schema="edu",
    )
    op.create_index(
        "ux_edu_certificates_attempt", "certificates", ["exam_attempt_id"],
        unique=True, schema="edu",
    )


def downgrade() -> None:

    op.drop_index("ux_edu_certificates_attempt", table_name="certificates", schema="edu")
    op.drop_index("ux_edu_certificates_code", table_name="certificates", schema="edu")
    op.drop_index("ux_edu_certificates_number", table_name="certificates", schema="edu")
    op.drop_table("certificates", schema="edu")
    op.drop_index("uq_edu_answers_attempt_question", table_name="exam_answers", schema="edu")
    op.drop_table("exam_answers", schema="edu")
    op.drop_index("ix_edu_attempts_status", table_name="exam_attempts", schema="edu")
    op.drop_index("ix_edu_attempts_user", table_name="exam_attempts", schema="edu")
    op.drop_index("ix_edu_attempts_exam", table_name="exam_attempts", schema="edu")
    op.drop_table("exam_attempts", schema="edu")
    op.drop_index("ix_edu_questions_exam", table_name="exam_questions", schema="edu")
    op.drop_table("exam_questions", schema="edu")
    op.drop_index("ix_edu_exams_course", table_name="course_exams", schema="edu")
    op.drop_table("course_exams", schema="edu")
    op.drop_index("uq_edu_grants_user_course", table_name="access_grants", schema="edu")
    op.drop_table("access_grants", schema="edu")
    op.drop_index("ix_edu_enroll_status", table_name="course_enrollments", schema="edu")
    op.drop_index("uq_edu_enroll_user_course", table_name="course_enrollments", schema="edu")
    op.drop_table("course_enrollments", schema="edu")
    op.drop_index("uq_edu_progress_user_lesson", table_name="lesson_progress", schema="edu")
    op.drop_table("lesson_progress", schema="edu")
    op.drop_index("ix_edu_lesson_versions_lesson", table_name="lesson_versions", schema="edu")
    op.drop_table("lesson_versions", schema="edu")
    op.drop_index("ix_edu_lessons_module", table_name="lessons", schema="edu")
    op.drop_table("lessons", schema="edu")
    op.drop_index("ix_edu_modules_course", table_name="course_modules", schema="edu")
    op.drop_table("course_modules", schema="edu")
    op.drop_index("ix_edu_courses_status", table_name="courses", schema="edu")
    op.drop_index("ux_edu_courses_slug", table_name="courses", schema="edu")
    op.drop_table("courses", schema="edu")
    op.drop_index("ix_content_topics_topic", table_name="content_topics", schema="content")
    op.drop_index("uq_content_topics_pair", table_name="content_topics", schema="content")
    op.drop_table("content_topics", schema="content")
    op.drop_index("ix_content_revisions_content", table_name="content_revisions", schema="content")
    op.drop_table("content_revisions", schema="content")
    op.drop_index("ix_content_contents_status", table_name="contents", schema="content")
    op.drop_index("ix_content_contents_type", table_name="contents", schema="content")
    op.drop_index("ux_content_contents_slug", table_name="contents", schema="content")
    op.drop_table("contents", schema="content")
