"""S6/B08: availability weekly rules + exceptions (schema booking)

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "availability_weekly_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.UniqueConstraint(
            "consultant_id", "weekday", "start_time", "end_time",
            name="ux_booking_weekly_rules_full",
        ),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["core.branches.id"], ondelete="SET NULL"),
        schema="booking",
    )
    op.create_index(
        "ix_booking_rules_consultant", "availability_weekly_rules", ["consultant_id"],
        schema="booking",
    )

    op.create_table(
        "availability_exceptions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("start_at", TSTZ, nullable=False),
        sa.Column("end_at", TSTZ, nullable=False),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="booking",
    )
    op.create_index(
        "ix_booking_exceptions_consultant", "availability_exceptions", ["consultant_id"],
        schema="booking",
    )


def downgrade() -> None:
    op.drop_table("availability_exceptions", schema="booking")
    op.drop_table("availability_weekly_rules", schema="booking")
