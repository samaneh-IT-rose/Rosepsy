"""S12/B41: consent_versions, consents, audit.access_events + immutability trigger

Revision ID: 0011
Revises: 0010
Create Date: 2025-01-11
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "consent_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title_fa", sa.String(150), nullable=False),
        sa.Column("text_fa", sa.String(5000), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.UniqueConstraint("kind", "version", name="ux_core_consent_versions_kind_ver"),
        schema="core",
    )
    op.create_index(
        "ix_core_consent_versions_kind", "consent_versions", ["kind"], schema="core"
    )

    op.create_table(
        "consents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version_id", UUID, nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="web"),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("granted_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("revoked_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["core.consent_versions.id"], ondelete="RESTRICT"),
        schema="core",
    )
    op.create_index("ix_core_consents_user", "consents", ["user_id"], schema="core")
    op.create_index("ix_core_consents_kind", "consents", ["kind"], schema="core")

    op.create_table(
        "access_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("subject_user_id", UUID, nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", UUID, nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("detail", JSONB, nullable=True),
        schema="audit",
    )
    op.create_index("ix_audit_access_actor", "access_events", ["actor_user_id"], schema="audit")
    op.create_index("ix_audit_access_subject", "access_events", ["subject_user_id"], schema="audit")

    op.execute(
        "CREATE OR REPLACE FUNCTION core.prevent_consent_version_mutation() "
        "RETURNS trigger AS $$ BEGIN "
        "RAISE EXCEPTION 'core.consent_versions is immutable'; "
        "END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER tr_consent_versions_immutable "
        "BEFORE UPDATE OR DELETE ON core.consent_versions "
        "FOR EACH ROW EXECUTE FUNCTION core.prevent_consent_version_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_consent_versions_immutable ON core.consent_versions")
    op.execute("DROP FUNCTION IF EXISTS core.prevent_consent_version_mutation()")
    op.drop_table("access_events", schema="audit")
    op.drop_table("consents", schema="core")
    op.drop_table("consent_versions", schema="core")
