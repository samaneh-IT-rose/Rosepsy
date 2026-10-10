"""S9/B12+B38: notification outbox, notifications, preferences, message threads

Revision ID: 0009
Revises: 0008
Create Date: 2025-01-09
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("processed_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ix_core_notif_events_status", "notification_events", ["status"], schema="core"
    )

    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("read_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index("ix_core_notifications_user", "notifications", ["user_id"], schema="core")

    op.create_table(
        "communication_preferences",
        sa.Column("user_id", UUID, primary_key=True),
        sa.Column("channel_sms", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("channel_email", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("channel_push", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )

    op.create_table(
        "message_threads",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("subject", sa.String(150), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="core",
    )

    op.create_table(
        "message_thread_members",
        sa.Column("thread_id", UUID, primary_key=True),
        sa.Column("user_id", UUID, primary_key=True),
        sa.ForeignKeyConstraint(["thread_id"], ["core.message_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("thread_id", UUID, nullable=False),
        sa.Column("sender_id", UUID, nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["core.message_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index("ix_core_messages_thread", "messages", ["thread_id"], schema="core")


def downgrade() -> None:
    op.drop_table("messages", schema="core")
    op.drop_table("message_thread_members", schema="core")
    op.drop_table("message_threads", schema="core")
    op.drop_table("communication_preferences", schema="core")
    op.drop_table("notifications", schema="core")
    op.drop_table("notification_events", schema="core")
