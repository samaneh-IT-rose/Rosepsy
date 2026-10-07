import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1000))
    logo_key: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    website: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="ck_core_branches_lat"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="ck_core_branches_lon"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.clinics.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    province: Mapped[str | None] = mapped_column(String(60))
    city: Mapped[str | None] = mapped_column(String(60), index=True)
    address: Mapped[str | None] = mapped_column(String(300))
    postal_code: Mapped[str | None] = mapped_column(String(10))
    working_hours: Mapped[dict | None] = mapped_column(JSONB)
    lat: Mapped[float] = mapped_column(Numeric(9, 6))
    lon: Mapped[float] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BranchServiceOffering(Base):
    __tablename__ = "branch_service_offerings"
    __table_args__ = (
        UniqueConstraint(
            "branch_id", "service_id", name="ux_core_branch_service_offerings"
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.branches.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.services.id", ondelete="CASCADE"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
