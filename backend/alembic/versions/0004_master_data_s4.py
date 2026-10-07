"""S4: specialties, services, consultants, credentials, verification_reviews, clinics, branches, offerings

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TSTZ = sa.DateTime(timezone=True)
NOW = sa.func.now()
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "specialties",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        schema="core",
    )
    op.create_index("ux_core_specialties_slug", "specialties", ["slug"], unique=True, schema="core")

    op.create_table(
        "services",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("specialty_id", UUID, nullable=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("session_type", sa.String(16), nullable=False, server_default="in_person"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("duration_minutes > 0", name="ck_core_services_duration_positive"),
        sa.ForeignKeyConstraint(["specialty_id"], ["core.specialties.id"], ondelete="SET NULL"),
        schema="core",
    )

    op.create_table(
        "consultants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("specialty_id", UUID, nullable=True),
        sa.Column("bio", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_review"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["specialty_id"], ["core.specialties.id"], ondelete="SET NULL"),
        schema="core",
    )
    op.create_index(
        "ux_core_consultants_user", "consultants", ["user_id"], unique=True, schema="core"
    )
    op.create_index("ix_core_consultants_status", "consultants", ["status"], schema="core")

    op.create_table(
        "credentials",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("license_number", sa.String(64), nullable=False),
        sa.Column("issued_by", sa.String(150), nullable=True),
        sa.Column("issued_at", TSTZ, nullable=True),
        sa.Column("expires_at", TSTZ, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("file_key", sa.String(255), nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ux_core_credentials_cons_license",
        "credentials",
        ["consultant_id", "license_number"],
        unique=True,
        schema="core",
    )
    op.create_index("ix_core_credentials_status", "credentials", ["status"], schema="core")

    op.create_table(
        "verification_reviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("consultant_id", UUID, nullable=False),
        sa.Column("credential_id", UUID, nullable=True),
        sa.Column("reviewer_id", UUID, nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["consultant_id"], ["core.consultants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_id"], ["core.credentials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["core.users.id"], ondelete="SET NULL"),
        schema="core",
    )

    op.create_table(
        "clinics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("logo_key", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("website", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        schema="core",
    )
    op.create_index("ux_core_clinics_slug", "clinics", ["slug"], unique=True, schema="core")

    op.create_table(
        "branches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("clinic_id", UUID, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("province", sa.String(60), nullable=True),
        sa.Column("city", sa.String(60), nullable=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("postal_code", sa.String(10), nullable=True),
        sa.Column("working_hours", JSONB, nullable=True),
        sa.Column("lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("lon", sa.Numeric(9, 6), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TSTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name="ck_core_branches_lat"),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name="ck_core_branches_lon"),
        sa.ForeignKeyConstraint(["clinic_id"], ["core.clinics.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index("ux_core_branches_slug", "branches", ["slug"], unique=True, schema="core")
    op.create_index("ix_core_branches_status", "branches", ["status"], schema="core")
    op.create_index("ix_core_branches_city", "branches", ["city"], schema="core")

    op.create_table(
        "branch_service_offerings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("service_id", UUID, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TSTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["core.branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["core.services.id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index(
        "ux_core_branch_service_offerings",
        "branch_service_offerings",
        ["branch_id", "service_id"],
        unique=True,
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("branch_service_offerings", schema="core")
    op.drop_table("branches", schema="core")
    op.drop_table("clinics", schema="core")
    op.drop_table("verification_reviews", schema="core")
    op.drop_table("credentials", schema="core")
    op.drop_table("consultants", schema="core")
    op.drop_table("services", schema="core")
    op.drop_table("specialties", schema="core")
