"""Authorization services for B04+: permission checks, branch scope, audit."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models.audit import AuditLog
from app.models.rbac import Permission, Role, RolePermission, UserRole


def has_permission(db: Session, user_id: uuid.UUID, code: str) -> bool:
    stmt = (
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, Permission.code == code)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def scoped_branch_ids(
    db: Session, user_id: uuid.UUID, permission_code: str
) -> set[uuid.UUID] | None:
    """Branch scope for a permission (ABAC light, spec s.12).

    None  => at least one grant has branch_id NULL => global access.
    set() => the user is restricted to exactly these branches.
    """
    stmt = (
        select(UserRole.branch_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user_id, Permission.code == permission_code)
    )
    rows = db.execute(stmt).scalars().all()
    if any(b is None for b in rows):
        return None
    return {b for b in rows if b is not None}


def write_audit(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None = None,
    action: str,
    outcome: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id or request_id_var.get(),
            ip=ip,
            detail=detail,
        )
    )
    db.commit()


def list_role_permissions(db: Session, role_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not role_ids:
        return {}
    rows = db.execute(
        select(RolePermission.role_id, Permission.code)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role_id.in_(role_ids))
    ).all()
    result: dict[uuid.UUID, list[str]] = {}
    for role_id, code in rows:
        result.setdefault(role_id, []).append(code)
    return result


def list_user_roles(db: Session, user_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
        .order_by(UserRole.created_at)
    ).all()
    return [
        {
            "id": str(grant.id),
            "role": role.name,
            "title_fa": role.title_fa,
            "branch_id": str(grant.branch_id) if grant.branch_id else None,
            "granted_at": grant.created_at.isoformat(),
        }
        for grant, role in rows
    ]


def grant_role(
    db: Session,
    *,
    user_id: uuid.UUID,
    role_name: str,
    granted_by: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> tuple[UserRole, bool]:
    """Returns (grant, created). Idempotent check at application level."""
    role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
    if role is None:
        raise ValueError(f"role not found: {role_name}")
    existing = db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    grant = UserRole(
        user_id=user_id, role_id=role.id, granted_by=granted_by, branch_id=branch_id
    )
    db.add(grant)
    db.commit()
    return grant, True


def revoke_role_grant(db: Session, user_id: uuid.UUID, grant_id: uuid.UUID) -> bool:
    grant = db.execute(
        select(UserRole).where(UserRole.id == grant_id, UserRole.user_id == user_id)
    ).scalar_one_or_none()
    if grant is None:
        return False
    db.delete(grant)
    db.commit()
    return True
