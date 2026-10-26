"""Release 3 · B21+B22+B23: organizations, accounting, feedback (surveys/tickets)

Revision ID: 0016
Revises: 0015
Create Date: 2025-01-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")

    # ── B21 organizations ──
    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("national_id", sa.String(20), nullable=False),
        sa.Column("contact_name", sa.String(120), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        schema="finance",
    )
    op.create_index(
        "ux_finance_organizations_national_id", "organizations", ["national_id"],
        unique=True, schema="finance",
    )

    op.create_table(
        "organization_contracts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("share_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("valid_from", TSTZ, nullable=False),
        sa.Column("valid_to", TSTZ, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "share_percent >= 0 AND share_percent <= 100",
            name="ck_finance_org_contracts_share",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["finance.organizations.id"], ondelete="CASCADE"
        ),
        schema="finance",
    )
    op.create_index(
        "ix_finance_org_contracts_org", "organization_contracts", ["organization_id"],
        schema="finance",
    )

    op.create_table(
        "organization_members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("valid_from", TSTZ, nullable=False),
        sa.Column("valid_to", TSTZ, nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["finance.organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ix_finance_org_members_org", "organization_members", ["organization_id"],
        schema="finance",
    )
    op.create_index(
        "ix_finance_org_members_user", "organization_members", ["user_id"], schema="finance"
    )

    # ── B22 accounting ──
    op.execute("CREATE SEQUENCE IF NOT EXISTS finance.journal_entry_seq START 1")
    op.create_table(
        "accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        schema="finance",
    )
    op.create_index("ux_finance_accounts_code", "accounts", ["code"], unique=True, schema="finance")

    op.create_table(
        "journal_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("entry_no", sa.String(30), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=True),
        sa.Column("source_id", UUID, nullable=True),
        sa.Column("posted_by", UUID, nullable=True),
        sa.Column("posted_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["posted_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ux_finance_journal_entries_no", "journal_entries", ["entry_no"], unique=True,
        schema="finance",
    )
    op.create_index(
        "ux_finance_journal_entries_source", "journal_entries",
        ["source_type", "source_id"], unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
        schema="finance",
    )

    op.create_table(
        "journal_lines",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("entry_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("debit", sa.Numeric(14, 0), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(14, 0), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (debit = 0 AND credit > 0)",
            name="ck_finance_journal_lines_one_side",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["finance.journal_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["finance.accounts.id"], ondelete="RESTRICT"
        ),
        schema="finance",
    )
    op.create_index(
        "ix_finance_journal_lines_entry", "journal_lines", ["entry_id"], schema="finance"
    )
    op.create_index(
        "ix_finance_journal_lines_account", "journal_lines", ["account_id"], schema="finance"
    )

    op.create_table(
        "settlements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("period_from", TSTZ, nullable=False),
        sa.Column("period_to", TSTZ, nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 0), nullable=False, server_default="0"),
        sa.Column("share_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(14, 0), nullable=False, server_default="0"),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("paid_at", TSTZ, nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["core.users.id"], ondelete="SET NULL"),
        schema="finance",
    )
    op.create_index(
        "ix_finance_settlements_consultant", "settlements", ["consultant_id"], schema="finance"
    )

    # ── B23 feedback ──
    op.create_table(
        "survey_responses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("appointment_id", UUID, nullable=True),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 10", name="ck_core_surveys_score_range"),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["booking.appointments.id"], ondelete="SET NULL"
        ),
        schema="core",
    )
    op.create_index(
        "ux_core_surveys_appointment", "survey_responses", ["appointment_id"],
        unique=True, postgresql_where=sa.text("appointment_id IS NOT NULL"),
        schema="core",
    )

    op.create_table(
        "support_tickets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("status", sa.String(14), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("resolved_at", TSTZ, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ix_core_tickets_user", "support_tickets", ["user_id"], schema="core"
    )
    op.create_index(
        "ix_core_tickets_status", "support_tickets", ["status"], schema="core"
    )

    op.create_table(
        "ticket_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticket_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("is_staff", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["core.support_tickets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ix_core_ticket_messages_ticket", "ticket_messages", ["ticket_id"], schema="core"
    )


def downgrade() -> None:
    op.drop_index("ix_core_ticket_messages_ticket", table_name="ticket_messages", schema="core")
    op.drop_table("ticket_messages", schema="core")
    op.drop_index("ix_core_tickets_status", table_name="support_tickets", schema="core")
    op.drop_index("ix_core_tickets_user", table_name="support_tickets", schema="core")
    op.drop_table("support_tickets", schema="core")
    op.drop_index("ux_core_surveys_appointment", table_name="survey_responses", schema="core")
    op.drop_table("survey_responses", schema="core")
    op.drop_index("ix_finance_settlements_consultant", table_name="settlements", schema="finance")
    op.drop_table("settlements", schema="finance")
    op.drop_index("ix_finance_journal_lines_account", table_name="journal_lines", schema="finance")
    op.drop_index("ix_finance_journal_lines_entry", table_name="journal_lines", schema="finance")
    op.drop_table("journal_lines", schema="finance")
    op.drop_index("ux_finance_journal_entries_source", table_name="journal_entries", schema="finance")
    op.drop_index("ux_finance_journal_entries_no", table_name="journal_entries", schema="finance")
    op.drop_table("journal_entries", schema="finance")
    op.execute("DROP SEQUENCE IF EXISTS finance.journal_entry_seq")
    op.drop_index("ux_finance_accounts_code", table_name="accounts", schema="finance")
    op.drop_table("accounts", schema="finance")
    op.drop_index("ix_finance_org_members_user", table_name="organization_members", schema="finance")
    op.drop_index("ix_finance_org_members_org", table_name="organization_members", schema="finance")
    op.drop_table("organization_members", schema="finance")
    op.drop_index("ix_finance_org_contracts_org", table_name="organization_contracts", schema="finance")
    op.drop_table("organization_contracts", schema="finance")
    op.drop_index("ux_finance_organizations_national_id", table_name="organizations", schema="finance")
    op.drop_table("organizations", schema="finance")
