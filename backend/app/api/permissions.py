"""Permission dependency factory (B04).

Rule from the spec: unauthorized access must be REJECTED and RECORDED at the
API level - hiding UI buttons is not sufficient.
"""


from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.core import User
from app.services.authz import has_permission, write_audit


def require_permission(code: str):
    def dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if has_permission(db, user.id, code):
            return user
        write_audit(
            db,
            actor_user_id=user.id,
            action=f"permission:{code}",
            outcome="denied",
            request_id=request_id_var.get(),
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    return dep
