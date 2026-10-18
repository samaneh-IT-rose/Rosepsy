"""Admin panel reference data (B42 — alignment with «سند ساختاریافته شناسایی صفحات»).

Entities required by the structured identification document:
- Province / City: regional search filters (users + centers pages, doc s.4.1 / s.6.3)
- ClinicGroup: «گروه‌بندی کلینیک‌ها» block on the centers page (doc s.6.2)
- Referral: «ارجاع» behind the user services table (doc s.5.3 — قرارداد، تعرفه کاربر،
  وضعیت) so every session row can resolve its referral context.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class Province(Base):
    """Provinces 1..31 of the province select; code 0 («کل کشور») is filter-only."""

    __tablename__ = "provinces"
    __table_args__ = {"schema": "core"}

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class City(Base):
    """City (شهرستان) options; filled dynamically per province (doc s.4.1)."""

    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("province_code", "name", name="ux_core_cities_province_name"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    province_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("core.provinces.code", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ClinicGroup(Base):
    """Clinic grouping created via addCenterCategory (doc s.6.2)."""

    __tablename__ = "clinic_groups"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Referral(Base):
    """«ارجاع» — authorization under which sessions (جلسات) are delivered.

    Carries the shared columns of the user services table (doc s.5.3/5.4):
    شناسه ارجاع (code), قرارداد (contract_title), تعرفه کاربر (user_tariff),
    وضعیت (status), مشاور و مرکز.
    """

    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint("user_tariff >= 0", name="ck_core_referrals_tariff_positive"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # «شناسه ارجاع» shown in the services table (numeric, sequence-backed).
    # Doc sample 100136613430 exceeds INT4 → BigInteger. server_default lets the
    # DB sequence assign the code when the ORM omits it.
    code: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        server_default=text("nextval('core.referrals_code_seq')"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), index=True
    )
    contract_title: Mapped[str | None] = mapped_column(String(150))
    user_tariff: Mapped[int] = mapped_column(Integer, default=0)
    # Status of the referral; sample data uses «در حال بررسی» (under_review).
    status: Mapped[str] = mapped_column(String(24), default="under_review", index=True)
    consultant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Source of the referral: «سها» referring organization (doc s.4.3 نحوه ثبت‌نام).
    source: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
