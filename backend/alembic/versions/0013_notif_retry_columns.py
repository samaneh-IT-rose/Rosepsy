"""B38: notification_events retry columns (attempts, last_error)

Revision ID: 0013
Revises: 0012
Create Date: 2025-01-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_events",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        schema="core",
    )
    op.add_column(
        "notification_events",
        sa.Column("last_error", sa.String(300), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("notification_events", "last_error", schema="core")
    op.drop_column("notification_events", "attempts", schema="core")
