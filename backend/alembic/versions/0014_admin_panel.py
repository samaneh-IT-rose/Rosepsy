"""B42 admin panel: geo reference, clinic groups, referrals, profile extensions.

Revision ID: 0014
Revises: 0013
Create Date: 2025-01-14

Alignment with «سند ساختاریافته شناسایی صفحات، فیلدها و ستون‌های سامانه»:
- core.provinces / core.cities  → regional search filters (doc s.4.1, s.6.3, s.9)
- core.clinic_groups            → «گروه‌بندی کلینیک‌ها» (doc s.6.2)
- core.referrals                → «ارجاع» behind the services table (doc s.5.3)
- core.profiles + columns       → «اطلاعات شخصی کاربر» (doc s.5.2)
- core.users.last_login_at      → «آخرین ورود» column (doc s.4.2)
- core.branches + columns       → grouping + legacy «شناسه جزئیات» (doc s.10)
- booking.appointments + columns→ session code / referral / «کیس حاد» (doc s.5.3)
Sequences back the numeric identifiers shown in the admin tables.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── provinces / cities (reference data for regional filters) ──
    op.create_table(
        "provinces",
        sa.Column("code", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        schema="core",
    )
    op.create_table(
        "cities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "province_code",
            sa.Integer(),
            sa.ForeignKey("core.provinces.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.UniqueConstraint("province_code", "name", name="ux_core_cities_province_name"),
        schema="core",
    )
    op.create_index("ix_core_cities_province_code", "cities", ["province_code"], schema="core")

    # ── clinic groups («گروه‌بندی کلینیک‌ها») ──
    op.create_table(
        "clinic_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="core",
    )

    # ── referrals («ارجاع») ──
    op.execute("CREATE SEQUENCE IF NOT EXISTS core.referrals_code_seq AS bigint START 100136613430")
    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "code",
            sa.BigInteger(),
            nullable=False,
            unique=True,
            server_default=sa.text("nextval('core.referrals_code_seq')"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("contract_title", sa.String(150), nullable=True),
        sa.Column("user_tariff", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="under_review"),
        sa.Column("consultant_id", sa.Uuid(), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(80), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("user_tariff >= 0", name="ck_core_referrals_tariff_positive"),
        schema="core",
    )
    op.create_index("ix_core_referrals_code", "referrals", ["code"], schema="core")
    op.create_index("ix_core_referrals_user_id", "referrals", ["user_id"], schema="core")
    op.create_index("ix_core_referrals_status", "referrals", ["status"], schema="core")

    # ── profiles: «اطلاعات شخصی کاربر» (doc s.5.2) + «کد» (doc s.4.2) ──
    op.execute("CREATE SEQUENCE IF NOT EXISTS core.profiles_code_seq START 463000")
    op.add_column(
        "profiles",
        sa.Column(
            "code",
            sa.Integer(),
            unique=True,
            server_default=sa.text("nextval('core.profiles_code_seq')"),
        ),
        schema="core",
    )
    op.add_column("profiles", sa.Column("username", sa.String(64)), schema="core")
    op.add_column("profiles", sa.Column("national_id", sa.String(10)), schema="core")
    op.add_column("profiles", sa.Column("father_name", sa.String(80)), schema="core")
    op.add_column("profiles", sa.Column("gender", sa.String(8)), schema="core")
    op.add_column("profiles", sa.Column("education", sa.String(40)), schema="core")
    op.add_column("profiles", sa.Column("marital_status", sa.String(12)), schema="core")
    op.add_column("profiles", sa.Column("birth_date", sa.Date()), schema="core")
    op.add_column("profiles", sa.Column("province_code", sa.Integer()), schema="core")
    op.add_column("profiles", sa.Column("city", sa.String(80)), schema="core")
    op.add_column("profiles", sa.Column("address", sa.String(300)), schema="core")
    op.add_column("profiles", sa.Column("postal_code", sa.String(10)), schema="core")
    op.add_column("profiles", sa.Column("email", sa.String(120)), schema="core")
    op.add_column("profiles", sa.Column("avatar_url", sa.String(300)), schema="core")
    op.add_column("profiles", sa.Column("registration_source", sa.String(80)), schema="core")
    op.create_index("ix_core_profiles_username", "profiles", ["username"], schema="core")
    op.create_index("ix_core_profiles_national_id", "profiles", ["national_id"], schema="core")
    op.create_index("ix_core_profiles_province_code", "profiles", ["province_code"], schema="core")

    # ── users: «آخرین ورود» (doc s.4.2) ──
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)), schema="core")

    # ── branches: grouping + legacy id (doc s.6 / s.10) ──
    op.add_column(
        "branches",
        sa.Column(
            "clinic_group_id",
            sa.Uuid(),
            sa.ForeignKey("core.clinic_groups.id", ondelete="SET NULL"),
        ),
        schema="core",
    )
    op.add_column("branches", sa.Column("legacy_code", sa.Integer()), schema="core")
    op.create_index("ix_core_branches_legacy_code", "branches", ["legacy_code"], schema="core")

    # ── appointments: session code / referral / «کیس حاد» (doc s.5.3) ──
    op.execute("CREATE SEQUENCE IF NOT EXISTS booking.appointments_code_seq START 279000")
    op.add_column(
        "appointments",
        sa.Column(
            "code",
            sa.Integer(),
            server_default=sa.text("nextval('booking.appointments_code_seq')"),
        ),
        schema="booking",
    )
    op.add_column(
        "appointments",
        sa.Column(
            "referral_id",
            sa.Uuid(),
            sa.ForeignKey("core.referrals.id", ondelete="SET NULL"),
        ),
        schema="booking",
    )
    op.add_column("appointments", sa.Column("acute_status", sa.String(12)), schema="booking")
    op.create_index("ix_booking_appointments_code", "appointments", ["code"], schema="booking")
    op.create_index(
        "ix_booking_appointments_referral_id", "appointments", ["referral_id"], schema="booking"
    )


def downgrade() -> None:
    op.drop_index("ix_booking_appointments_referral_id", "appointments", schema="booking")
    op.drop_index("ix_booking_appointments_code", "appointments", schema="booking")
    op.drop_column("appointments", "acute_status", schema="booking")
    op.drop_column("appointments", "referral_id", schema="booking")
    op.drop_column("appointments", "code", schema="booking")
    op.execute("DROP SEQUENCE IF EXISTS booking.appointments_code_seq")
    op.drop_index("ix_core_branches_legacy_code", "branches", schema="core")
    op.drop_column("branches", "legacy_code", schema="core")
    op.drop_column("branches", "clinic_group_id", schema="core")
    op.drop_column("users", "last_login_at", schema="core")
    op.drop_index("ix_core_profiles_province_code", "profiles", schema="core")
    op.drop_index("ix_core_profiles_national_id", "profiles", schema="core")
    op.drop_index("ix_core_profiles_username", "profiles", schema="core")
    for col in (
        "registration_source",
        "avatar_url",
        "email",
        "postal_code",
        "address",
        "city",
        "province_code",
        "birth_date",
        "marital_status",
        "education",
        "gender",
        "father_name",
        "national_id",
        "username",
        "code",
    ):
        op.drop_column("profiles", col, schema="core")
    op.execute("DROP SEQUENCE IF EXISTS core.profiles_code_seq")
    op.drop_index("ix_core_referrals_status", "referrals", schema="core")
    op.drop_index("ix_core_referrals_user_id", "referrals", schema="core")
    op.drop_index("ix_core_referrals_code", "referrals", schema="core")
    op.drop_table("referrals", schema="core")
    op.execute("DROP SEQUENCE IF EXISTS core.referrals_code_seq")
    op.drop_table("clinic_groups", schema="core")
    op.drop_index("ix_core_cities_province_code", "cities", schema="core")
    op.drop_table("cities", schema="core")
    op.drop_table("provinces", schema="core")
