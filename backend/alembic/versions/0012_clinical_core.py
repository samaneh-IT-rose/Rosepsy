"""S13+S14/B13-B16: clinical records, questionnaires, encounters, notes

Revision ID: 0012
Revises: 0011
Create Date: 2025-01-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS clinical")

    op.create_table(
        "clinical_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("summary", sa.String(1000), nullable=True),
        sa.Column("risk_level", sa.String(12), nullable=False, server_default="unknown"),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )
    op.create_index(
        "ux_clinical_records_user", "clinical_records", ["user_id"], unique=True,
        schema="clinical",
    )

    op.create_table(
        "record_files",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("record_id", UUID, nullable=False),
        sa.Column("file_id", UUID, nullable=False),
        sa.Column("attached_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["clinical.clinical_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["core.files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attached_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )

    op.create_table(
        "questionnaires",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title_fa", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )
    op.create_index(
        "ux_clinical_questionnaires_slug", "questionnaires", ["slug"], unique=True,
        schema="clinical",
    )

    op.create_table(
        "questionnaire_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("questionnaire_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_json", JSONB, nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.UniqueConstraint("questionnaire_id", "version", name="ux_clin_qv_q_ver"),
        sa.ForeignKeyConstraint(
            ["questionnaire_id"], ["clinical.questionnaires.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )

    op.create_table(
        "submissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("record_id", UUID, nullable=False),
        sa.Column("version_id", UUID, nullable=False),
        sa.Column("answers", JSONB, nullable=False),
        sa.Column("submitted_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"], ["clinical.clinical_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], ["clinical.questionnaire_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["submitted_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )
    op.create_index("ix_clinical_submissions_record", "submissions", ["record_id"],
                    schema="clinical")

    op.create_table(
        "encounters",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("record_id", UUID, nullable=False),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("appointment_id", UUID, nullable=True),
        sa.Column("start_at", TSTZ, nullable=False),
        sa.Column("end_at", TSTZ, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("end_at > start_at", name="ck_clinical_encounters_range"),
        sa.ForeignKeyConstraint(
            ["record_id"], ["clinical.clinical_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["booking.appointments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )
    op.create_index("ix_clinical_encounters_record", "encounters", ["record_id"],
                    schema="clinical")

    op.create_table(
        "encounter_notes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("encounter_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=True),
        sa.Column("body", sa.String(5000), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["clinical.encounters.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )
    op.create_index("ix_clinical_notes_encounter", "encounter_notes", ["encounter_id"],
                    schema="clinical")

    op.create_table(
        "encounter_amendments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("note_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=True),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("body", sa.String(5000), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"], ["clinical.encounter_notes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["core.users.id"], ondelete="SET NULL"),
        schema="clinical",
    )


def downgrade() -> None:
    op.drop_table("encounter_amendments", schema="clinical")
    op.drop_table("encounter_notes", schema="clinical")
    op.drop_table("encounters", schema="clinical")
    op.drop_table("submissions", schema="clinical")
    op.drop_table("questionnaire_versions", schema="clinical")
    op.drop_table("questionnaires", schema="clinical")
    op.drop_table("record_files", schema="clinical")
    op.drop_table("clinical_records", schema="clinical")
