"""B02: core auth tables (users, profiles, otp_challenges, auth_sessions)

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        schema="core",
    )
    op.create_index(
        "ux_core_users_phone_e164", "users", ["phone_e164"], unique=True, schema="core"
    )

    op.create_table(
        "profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("first_name", sa.String(80), nullable=True),
        sa.Column("last_name", sa.String(80), nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )

    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="login"),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", TSTZ, nullable=False),
        sa.Column("locked_until", TSTZ, nullable=True),
        sa.Column("consumed_at", TSTZ, nullable=True),
        sa.Column("request_ip", sa.String(45), nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        schema="core",
    )
    op.create_index("ix_core_otp_phone", "otp_challenges", ["phone_e164"], schema="core")

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("expires_at", TSTZ, nullable=False),
        sa.Column("revoked_at", TSTZ, nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ux_core_auth_sessions_token", "auth_sessions", ["token_hash"], unique=True, schema="core"
    )
    op.create_index(
        "ix_core_auth_sessions_user", "auth_sessions", ["user_id"], schema="core"
    )


def downgrade() -> None:
    op.drop_index("ix_core_auth_sessions_user", schema="core")
    op.drop_index("ux_core_auth_sessions_token", schema="core")
    op.drop_table("auth_sessions", schema="core")
    op.drop_index("ix_core_otp_phone", schema="core")
    op.drop_table("otp_challenges", schema="core")
    op.drop_table("profiles", schema="core")
    op.drop_index("ux_core_users_phone_e164", schema="core")
    op.drop_table("users", schema="core")
