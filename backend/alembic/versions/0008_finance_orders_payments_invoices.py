"""S8/B10+B11: finance orders, payments, invoices, invoice_items

Revision ID: 0008
Revises: 0007
Create Date: 2025-01-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")
    op.execute("CREATE SEQUENCE IF NOT EXISTS finance.invoice_number_seq START 1")

    op.create_table(
        "orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("appointment_id", UUID, nullable=True),
        sa.Column("order_type", sa.String(20), nullable=False, server_default="appointment"),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="IRR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="awaiting_payment"),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.Column("price_snapshot", JSONB, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_finance_orders_amount_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["booking.appointments.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ux_finance_orders_user_idem", "orders", ["user_id", "idempotency_key"],
        unique=True, schema="finance",
    )
    op.create_index("ix_finance_orders_status", "orders", ["status"], schema="finance")

    op.create_table(
        "payments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("gateway", sa.String(20), nullable=False, server_default="mock"),
        sa.Column("gateway_ref", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="IRR"),
        sa.Column("status", sa.String(16), nullable=False, server_default="initiated"),
        sa.Column("raw_callback", JSONB, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("verified_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="CASCADE"),
        schema="finance",
    )
    op.create_index(
        "ux_finance_payments_ref", "payments", ["gateway_ref"], unique=True, schema="finance"
    )

    op.create_table(
        "invoices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("invoice_number", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="IRR"),
        sa.Column("issued_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="CASCADE"),
        schema="finance",
    )
    op.create_index(
        "ux_finance_invoices_order", "invoices", ["order_id"], unique=True, schema="finance"
    )
    op.create_index(
        "ux_finance_invoices_number", "invoices", ["invoice_number"], unique=True, schema="finance"
    )

    op.create_table(
        "invoice_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("invoice_id", UUID, nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("total", sa.Numeric(14, 0), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["finance.invoices.id"], ondelete="CASCADE"),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_table("invoice_items", schema="finance")
    op.drop_table("invoices", schema="finance")
    op.drop_table("payments", schema="finance")
    op.drop_table("orders", schema="finance")
    op.execute("DROP SEQUENCE IF EXISTS finance.invoice_number_seq")
