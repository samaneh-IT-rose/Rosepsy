"""Price lookup core shared by the quote endpoint and booking (B07/B09)."""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.pricing import Tariff, TariffVersion


def find_tariff(
    db: Session, *, service_id, branch_id=None
) -> Tariff | None:
    """Branch-specific tariff wins over the service-global one."""
    if branch_id is not None:
        t = db.execute(
            select(Tariff).where(
                Tariff.service_id == service_id,
                Tariff.branch_id == branch_id,
                Tariff.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if t is not None:
            return t
    return db.execute(
        select(Tariff).where(
            Tariff.service_id == service_id,
            Tariff.branch_id.is_(None),
            Tariff.is_active.is_(True),
        )
    ).scalar_one_or_none()


def applicable_version(db: Session, *, tariff: Tariff, at: datetime) -> TariffVersion | None:
    return db.execute(
        select(TariffVersion)
        .where(
            TariffVersion.tariff_id == tariff.id,
            TariffVersion.valid_from <= at,
            or_(TariffVersion.valid_to.is_(None), TariffVersion.valid_to > at),
        )
        .order_by(TariffVersion.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()
