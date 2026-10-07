"""S7/B09: slot_claims + appointments with anti-overlap exclusion constraints

Revision ID: 0007
Revises: 0006
Create Date: 2025-01-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "slot_claims",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("service_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("start_at", TSTZ, nullable=False),
        sa.Column("end_at", TSTZ, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="held"),
        sa.Column("expires_at", TSTZ, nullable=False),
        sa.Column("price_snapshot", JSONB, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["core.services.id"], ondelete="CASCADE"),
        schema="booking",
    )
    op.create_index("ix_booking_claims_user", "slot_claims", ["user_id"], schema="booking")
    op.execute(
        "ALTER TABLE booking.slot_claims ADD CONSTRAINT ex_booking_slot_claims_active "
        "EXCLUDE USING gist (consultant_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) "
        "WHERE (status = 'held')"
    )

    op.create_table(
        "appointments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("service_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=True),
        sa.Column("hold_id", UUID, nullable=True),
        sa.Column("start_at", TSTZ, nullable=False),
        sa.Column("end_at", TSTZ, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_payment"),
        sa.Column("price_snapshot", JSONB, nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["core.services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hold_id"], ["booking.slot_claims.id"], ondelete="SET NULL"),
        schema="booking",
    )
    op.create_index(
        "ix_booking_appointments_user", "appointments", ["user_id"], schema="booking"
    )
    op.execute(
        "ALTER TABLE booking.appointments ADD CONSTRAINT ex_booking_appointments_active "
        "EXCLUDE USING gist (consultant_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) "
        "WHERE (status IN ('pending_payment', 'confirmed', 'in_progress'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE booking.appointments DROP CONSTRAINT IF EXISTS ex_booking_appointments_active")
    op.drop_table("appointments", schema="booking")
    op.execute("ALTER TABLE booking.slot_claims DROP CONSTRAINT IF EXISTS ex_booking_slot_claims_active")
    op.drop_table("slot_claims", schema="booking")
