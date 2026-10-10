"""Clinical access core (B13): the golden rule lives here.

Every sensitive read MUST call assert_record_read - it checks permission and
writes an audit.access_events row (allowed or denied) before anything else.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models.catalog import Consultant
from app.models.clinical import Encounter
from app.models.core import User
from app.services.authz import has_permission, write_access_event


def user_is_consultant(db: Session, user: User) -> Consultant | None:
    return db.execute(
        select(Consultant).where(Consultant.user_id == user.id)
    ).scalar_one_or_none()


def consultant_has_relationship(
    db: Session, consultant_id: uuid.UUID, record_id: uuid.UUID
) -> bool:
    """A consultant may read a record only if an encounter links them."""
    return (
        db.execute(
            select(Encounter.id)
            .where(
                Encounter.record_id == record_id,
                Encounter.consultant_id == consultant_id,
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def assert_record_read(
    db: Session,
    *,
    user: User,
    record_id: uuid.UUID,
    request_ip: str | None = None,
) -> tuple[bool, str | None]:
    """Returns (allowed, error_code). ALWAYS writes an access event first.

    Allowed: the record owner, or a consultant with an encounter relationship
    (permission records.read is implicit in the relationship, per spec role
    table: consultant sees records of their own clients only).
    """
    allowed = False
    reason = ""

    if has_permission(db, user.id, "records.read"):
        cons = user_is_consultant(db, user)
        if cons is not None and consultant_has_relationship(db, cons.id, record_id):
            allowed = True
            reason = "consultant_of_client"
        else:
            # DPO-style readers are NOT granted clinical text per spec; only
            # explicit records.read holders with relationship pass here.
            reason = "no_relationship"
    else:
        # owner check happens via record.user_id == user.id by the caller;
        # here we mark non-owner non-consultant attempts.
        reason = "not_owner"

    write_access_event(
        db,
        actor_user_id=user.id,
        action="clinical.record.read",
        allowed=allowed,
        resource_type="clinical_record",
        resource_id=record_id,
        request_id=request_id_var.get(),
        ip=request_ip,
        detail={"reason": reason},
    )
    return allowed, (None if allowed else "FORBIDDEN")
