import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.core import User
from app.models.rbac import Role
from app.services.authz import (
    grant_role,
    list_role_permissions,
    list_user_roles,
    revoke_role_grant,
    write_audit,
)

router = APIRouter(tags=["roles"])


class RoleAssignIn(BaseModel):
    role: str = Field(min_length=2, max_length=50)
    branch_id: uuid.UUID | None = None


@router.get("/roles")
def list_roles(
    user: User = Depends(require_permission("roles.read")),
    db: Session = Depends(get_db),
):
    roles = (
        db.execute(select(Role).where(Role.is_active.is_(True)).order_by(Role.name))
        .scalars()
        .all()
    )
    perms = list_role_permissions(db, [r.id for r in roles])
    return envelope(
        data=[
            {
                "id": str(r.id),
                "name": r.name,
                "title_fa": r.title_fa,
                "description": r.description,
                "permissions": sorted(perms.get(r.id, [])),
            }
            for r in roles
        ]
    )


@router.get("/users/{user_id}/roles")
def get_user_roles(
    user_id: uuid.UUID,
    user: User = Depends(require_permission("roles.read")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    return envelope(data=list_user_roles(db, target.id))


@router.post("/users/{user_id}/roles", status_code=201)
def assign_role(
    user_id: uuid.UUID,
    body: RoleAssignIn,
    user: User = Depends(require_permission("roles.assign")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    try:
        grant, created = grant_role(
            db,
            user_id=target.id,
            role_name=body.role,
            granted_by=user.id,
            branch_id=body.branch_id,
        )
    except ValueError:
        return error_response("ROLE_NOT_FOUND", "نقش یافت نشد", 404)
    if not created:
        return error_response("ROLE_ALREADY_ASSIGNED", "این نقش قبلاً داده شده است", 409)
    write_audit(
        db,
        actor_user_id=user.id,
        action="role.assign",
        outcome="allowed",
        resource_type="user",
        resource_id=target.id,
        request_id=request_id_var.get(),
        detail={"role": body.role},
    )
    return envelope(
        data={"grant_id": str(grant.id), "user_id": str(target.id), "role": body.role}
    )


@router.delete("/users/{user_id}/roles/{grant_id}")
def revoke_role(
    user_id: uuid.UUID,
    grant_id: uuid.UUID,
    user: User = Depends(require_permission("roles.assign")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    ok = revoke_role_grant(db, target.id, grant_id)
    if not ok:
        return error_response("ROLE_GRANT_NOT_FOUND", "تخصیص نقش یافت نشد", 404)
    write_audit(
        db,
        actor_user_id=user.id,
        action="role.revoke",
        outcome="allowed",
        resource_type="user",
        resource_id=target.id,
        request_id=request_id_var.get(),
    )
    return envelope(data={"revoked": True, "user_id": str(target.id)})
