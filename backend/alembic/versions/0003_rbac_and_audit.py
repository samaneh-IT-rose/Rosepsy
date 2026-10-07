"""B03/B04: rbac tables + audit.audit_logs

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("title_fa", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        schema="core",
    )
    op.create_index("ux_core_roles_name", "roles", ["name"], unique=True, schema="core")

    op.create_table(
        "permissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("title_fa", sa.String(100), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        schema="core",
    )
    op.create_index(
        "ux_core_permissions_code", "permissions", ["code"], unique=True, schema="core"
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, primary_key=True),
        sa.Column("permission_id", UUID, primary_key=True),
        sa.ForeignKeyConstraint(["role_id"], ["core.roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["core.permissions.id"], ondelete="CASCADE"),
        schema="core",
    )

    op.create_table(
        "user_roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role_id", UUID, nullable=False),
        sa.Column("granted_by", UUID, nullable=True),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["core.roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="core",
    )
    op.create_index(
        "ux_core_user_roles_user_role",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        schema="core",
    )

    op.create_table(
        "applicants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="core",
    )
    op.create_index("ix_core_applicants_phone", "applicants", ["phone_e164"], schema="core")

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", UUID, nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        schema="audit",
    )
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_user_id"], schema="audit")
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], schema="audit")


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action", schema="audit")
    op.drop_index("ix_audit_logs_actor", schema="audit")
    op.drop_table("audit_logs", schema="audit")
    op.drop_index("ix_core_applicants_phone", schema="core")
    op.drop_table("applicants", schema="core")
    op.drop_index("ux_core_user_roles_user_role", schema="core")
    op.drop_table("user_roles", schema="core")
    op.drop_table("role_permissions", schema="core")
    op.drop_index("ux_core_permissions_code", schema="core")
    op.drop_table("permissions", schema="core")
    op.drop_index("ux_core_roles_name", schema="core")
    op.drop_table("roles", schema="core")
