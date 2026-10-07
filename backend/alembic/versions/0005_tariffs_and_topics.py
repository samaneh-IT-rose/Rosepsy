"""S5: tariffs, tariff_versions, topics

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("service_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["core.services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["core.branches.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ux_core_tariffs_service_global",
        "tariffs",
        ["service_id"],
        unique=True,
        schema="core",
        postgresql_where=sa.text("branch_id IS NULL"),
    )
    op.create_index(
        "ix_core_tariffs_service_branch", "tariffs", ["service_id", "branch_id"], schema="core"
    )

    op.create_table(
        "tariff_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tariff_id", UUID, nullable=False),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="IRR"),
        sa.Column("valid_from", TSTZ, nullable=False),
        sa.Column("valid_to", TSTZ, nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_core_tariff_versions_range",
        ),
        sa.ForeignKeyConstraint(["tariff_id"], ["core.tariffs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="core",
    )
    op.create_index(
        "ix_core_tariff_versions_tariff", "tariff_versions", ["tariff_id"], schema="core"
    )

    op.create_table(
        "topics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["core.topics.id"], ondelete="SET NULL"),
        schema="core",
    )
    op.create_index("ux_core_topics_slug", "topics", ["slug"], unique=True, schema="core")
    op.create_index("ix_core_topics_parent", "topics", ["parent_id"], schema="core")


def downgrade() -> None:
    op.drop_table("topics", schema="core")
    op.drop_table("tariff_versions", schema="core")
    op.drop_table("tariffs", schema="core")
