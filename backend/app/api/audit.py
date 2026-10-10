
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope
from app.core.db import get_db
from app.models.audit import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit/access")
def access_report(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("audit.access.read")),
    db: Session = Depends(get_db),
):
    """Denied-access report (B41 acceptance) - DPO/auditor scope."""
    base = select(AuditLog).where(AuditLog.outcome == "denied")
    total = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.outcome == "denied")
    ).scalar_one()
    rows = (
        db.execute(base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat(),
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "request_id": r.request_id,
                "ip": r.ip,
            }
            for r in rows
        ],
        extra_meta={"total": total, "limit": limit, "offset": offset},
    )
