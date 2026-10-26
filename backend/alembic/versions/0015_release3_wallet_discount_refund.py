"""Release 3 · B18+B19+B20: wallets, discounts, refunds

Revision ID: 0015
Revises: 0014
Create Date: 2025-01-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")

    # ── B18 wallet ──
    op.create_table(
        "wallets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="IRR"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="finance",
    )
    op.create_index("ux_finance_wallets_user", "wallets", ["user_id"], unique=True, schema="finance")

    op.create_table(
        "wallet_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("wallet_id", UUID, nullable=False),
        sa.Column("direction", sa.String(6), nullable=False),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 0), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("order_id", UUID, nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_finance_wallet_entries_amount_positive"),
        sa.CheckConstraint(
            "direction IN ('credit','debit')", name="ck_finance_wallet_entries_direction"
        ),
        sa.ForeignKeyConstraint(["wallet_id"], ["finance.wallets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ix_finance_wallet_entries_wallet", "wallet_entries", ["wallet_id"], schema="finance"
    )
    op.create_index(
        "ux_finance_wallet_entries_wallet_idem",
        "wallet_entries",
        ["wallet_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        schema="finance",
    )

    # ── B19 discounts ──
    op.create_table(
        "discounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False, server_default="fixed"),
        sa.Column("value", sa.Numeric(14, 0), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(14, 0), nullable=False, server_default="0"),
        sa.Column("max_redemptions_total", sa.Integer, nullable=True),
        sa.Column("max_redemptions_per_user", sa.Integer, nullable=True),
        sa.Column("starts_at", TSTZ, nullable=True),
        sa.Column("ends_at", TSTZ, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("value > 0", name="ck_finance_discounts_value_positive"),
        sa.CheckConstraint("kind IN ('percent','fixed')", name="ck_finance_discounts_kind"),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index("ux_finance_discounts_code", "discounts", ["code"], unique=True, schema="finance")

    op.create_table(
        "discount_redemptions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("discount_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("amount_applied", sa.Numeric(14, 0), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["discount_id"], ["finance.discounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="CASCADE"),
        schema="finance",
    )
    op.create_index(
        "ix_finance_redemptions_discount", "discount_redemptions", ["discount_id"], schema="finance"
    )
    op.create_index(
        "ix_finance_redemptions_user", "discount_redemptions", ["user_id"], schema="finance"
    )
    op.create_index(
        "uq_finance_redemptions_order", "discount_redemptions", ["order_id"],
        unique=True, schema="finance",
    )

    # order gets discount columns (B19)
    op.add_column(
        "orders",
        sa.Column("discount_id", UUID, nullable=True),
        schema="finance",
    )
    op.add_column(
        "orders",
        sa.Column(
            "discount_amount", sa.Numeric(14, 0), nullable=False, server_default="0"
        ),
        schema="finance",
    )
    op.create_foreign_key(
        "fk_finance_orders_discount",
        "orders",
        "discounts",
        ["discount_id"],
        ["id"],
        source_schema="finance",
        referent_schema="finance",
        ondelete="SET NULL",
    )

    # ── B20 refunds ──
    op.create_table(
        "refund_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="submitted"),
        sa.Column("decided_by", UUID, nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_finance_refund_requests_amount_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["finance.orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ix_finance_refund_requests_order", "refund_requests", ["order_id"], schema="finance"
    )
    op.create_index(
        "ix_finance_refund_requests_user", "refund_requests", ["user_id"], schema="finance"
    )
    op.create_index(
        "ix_finance_refund_requests_status", "refund_requests", ["status"], schema="finance"
    )

    op.create_table(
        "refunds",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("refund_request_id", UUID, nullable=False),
        sa.Column("payment_id", UUID, nullable=True),
        sa.Column("wallet_entry_id", UUID, nullable=True),
        sa.Column("amount", sa.Numeric(14, 0), nullable=False),
        sa.Column("executed_by", UUID, nullable=True),
        sa.Column("executed_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["refund_request_id"], ["finance.refund_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["finance.payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["wallet_entry_id"], ["finance.wallet_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["executed_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ux_finance_refunds_request", "refunds", ["refund_request_id"], unique=True, schema="finance"
    )


def downgrade() -> None:
    op.drop_index("ux_finance_refunds_request", table_name="refunds", schema="finance")
    op.drop_table("refunds", schema="finance")
    op.drop_index("ix_finance_refund_requests_status", table_name="refund_requests", schema="finance")
    op.drop_index("ix_finance_refund_requests_user", table_name="refund_requests", schema="finance")
    op.drop_index("ix_finance_refund_requests_order", table_name="refund_requests", schema="finance")
    op.drop_table("refund_requests", schema="finance")
    op.drop_constraint("fk_finance_orders_discount", "orders", schema="finance", type_="foreignkey")
    op.drop_column("orders", "discount_amount", schema="finance")
    op.drop_column("orders", "discount_id", schema="finance")
    op.drop_index("uq_finance_redemptions_order", table_name="discount_redemptions", schema="finance")
    op.drop_index("ix_finance_redemptions_user", table_name="discount_redemptions", schema="finance")
    op.drop_index("ix_finance_redemptions_discount", table_name="discount_redemptions", schema="finance")
    op.drop_table("discount_redemptions", schema="finance")
    op.drop_index("ux_finance_discounts_code", table_name="discounts", schema="finance")
    op.drop_table("discounts", schema="finance")
    op.drop_index(
        "ux_finance_wallet_entries_wallet_idem", table_name="wallet_entries", schema="finance"
    )
    op.drop_index("ix_finance_wallet_entries_wallet", table_name="wallet_entries", schema="finance")
    op.drop_table("wallet_entries", schema="finance")
    op.drop_index("ux_finance_wallets_user", table_name="wallets", schema="finance")
    op.drop_table("wallets", schema="finance")
