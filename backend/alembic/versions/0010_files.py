"""S10/B39: core.files

Revision ID: 0010
Revises: 0009
Create Date: 2025-01-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("owner_user_id", UUID, nullable=False),
        sa.Column("context", sa.String(32), nullable=False, server_default="general"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="uploaded"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index("ix_core_files_owner", "files", ["owner_user_id"], schema="core")
    op.create_index("ix_core_files_status", "files", ["status"], schema="core")
    op.create_index(
        "ux_core_files_key", "files", ["storage_key"], unique=True, schema="core"
    )


def downgrade() -> None:
    op.drop_table("files", schema="core")
