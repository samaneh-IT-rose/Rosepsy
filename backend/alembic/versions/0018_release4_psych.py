"""Release 4 · B37: psychology tests, versioned questions, interpretation rules.

Revision ID: 0018
Revises: 0017
Create Date: 2025-01-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS psych")

    op.create_table(
        "psych_tests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("purpose", sa.String(1000), nullable=True),
        sa.Column("target_population", sa.String(300), nullable=True),
        sa.Column("age_min", sa.Integer, nullable=True),
        sa.Column("age_max", sa.Integer, nullable=True),
        sa.Column("consent_kind", sa.String(40), nullable=False, server_default="psych_test"),
        sa.Column("scientific_doc", sa.String(300), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_psych_tests_status"
        ),
        sa.CheckConstraint(
            "(age_min IS NULL OR age_min >= 0) AND (age_max IS NULL OR age_max <= 120)",
            name="ck_psych_tests_age_range",
        ),
        schema="psych",
    )
    op.create_index("ux_psych_tests_code", "psych_tests", ["code"], unique=True, schema="psych")
    op.create_index("ix_psych_tests_status", "psych_tests", ["status"], schema="psych")

    op.create_table(
        "psych_test_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("test_id", UUID, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("scale_label", sa.String(120), nullable=False),
        sa.Column("scoring_method", sa.String(12), nullable=False, server_default="sum"),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("approved_by", UUID, nullable=True),
        sa.Column("approved_at", TSTZ, nullable=True),
        sa.Column("published_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.UniqueConstraint("test_id", "version", name="ux_psych_versions_test_ver"),
        sa.CheckConstraint(
            "status IN ('draft','approved','published','archived')",
            name="ck_psych_versions_status",
        ),
        sa.CheckConstraint("scoring_method IN ('sum')", name="ck_psych_versions_scoring"),
        sa.ForeignKeyConstraint(
            ["test_id"], ["psych.psych_tests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="psych",
    )
    op.create_index(
        "ix_psych_versions_test", "psych_test_versions", ["test_id"], schema="psych"
    )
    op.create_index(
        "ix_psych_versions_status", "psych_test_versions", ["status"], schema="psych"
    )

    op.create_table(
        "psych_questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("version_id", UUID, nullable=False),
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("position", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["psych.psych_test_versions.id"], ondelete="CASCADE"
        ),
        schema="psych",
    )
    op.create_index(
        "ix_psych_questions_version", "psych_questions", ["version_id"], schema="psych"
    )

    op.create_table(
        "psych_interpretation_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("version_id", UUID, nullable=False),
        sa.Column("min_score", sa.Integer, nullable=False),
        sa.Column("max_score", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("guidance", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("approved_by", UUID, nullable=True),
        sa.Column("approved_at", TSTZ, nullable=True),
        sa.CheckConstraint("min_score <= max_score", name="ck_psych_rules_band"),
        sa.CheckConstraint("status IN ('draft','approved')", name="ck_psych_rules_status"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["psych.psych_test_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="psych",
    )
    op.create_index(
        "ix_psych_rules_version",
        "psych_interpretation_rules",
        ["version_id"],
        schema="psych",
    )

    op.create_table(
        "psych_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("test_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("version_id", UUID, nullable=False),
        sa.Column("consent_id", UUID, nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="started"),
        sa.Column("raw_score", sa.Integer, nullable=True),
        sa.Column("rule_id", UUID, nullable=True),
        sa.Column("interpretation_title", sa.String(200), nullable=True),
        sa.Column("interpretation_text", sa.String(2000), nullable=True),
        sa.Column("started_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("consented_at", TSTZ, nullable=True),
        sa.Column("submitted_at", TSTZ, nullable=True),
        sa.Column("scored_at", TSTZ, nullable=True),
        sa.Column("reviewed_by", UUID, nullable=True),
        sa.Column("reviewed_at", TSTZ, nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
        sa.CheckConstraint(
            "status IN ('started','consented','in_progress','scored','reviewed','abandoned')",
            name="ck_psych_attempts_status",
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["psych.psych_tests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["psych.psych_test_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"], ["core.consents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["psych.psych_interpretation_rules.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="psych",
    )
    op.create_index("ix_psych_attempts_test", "psych_attempts", ["test_id"], schema="psych")
    op.create_index("ix_psych_attempts_user", "psych_attempts", ["user_id"], schema="psych")
    op.create_index(
        "ix_psych_attempts_version", "psych_attempts", ["version_id"], schema="psych"
    )
    op.create_index("ix_psych_attempts_status", "psych_attempts", ["status"], schema="psych")

    op.create_table(
        "psych_answers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("question_id", UUID, nullable=False),
        sa.Column("option_index", sa.Integer, nullable=False),
        sa.Column("option_score", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_psych_answers_attempt_q"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["psych.psych_attempts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["psych.psych_questions.id"], ondelete="RESTRICT"
        ),
        schema="psych",
    )
    op.create_index(
        "ix_psych_answers_attempt", "psych_answers", ["attempt_id"], schema="psych"
    )


def downgrade() -> None:
    op.drop_table("psych_answers", schema="psych")
    op.drop_table("psych_attempts", schema="psych")
    op.drop_table("psych_interpretation_rules", schema="psych")
    op.drop_table("psych_questions", schema="psych")
    op.drop_table("psych_test_versions", schema="psych")
    op.drop_table("psych_tests", schema="psych")
    op.execute("DROP SCHEMA IF EXISTS psych")
