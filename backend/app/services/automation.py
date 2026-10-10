"""Release-2 step 1 (B09<->B13/B15): automatic fulfillment of a paid appointment.

Called INSIDE the payments callback transaction (no commit here) so the
payment confirmation, clinical record and encounter are atomic together.

Rules (spec BPMN process 03 + consent precedence):
- No active treatment consent  -> NO clinical writes; a consent.required
  notification event is enqueued for the owner.
- Record: reused if it exists, otherwise created (system actor).
- Encounter: created once per appointment (unique appointment_id), linked to
  the record, status=scheduled - only if the consultant is still bookable;
  otherwise system_admin users get an encounter.auto_create_failed event.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AccessEvent
from app.models.booking import Appointment
from app.models.catalog import Consultant
from app.models.clinical import ClinicalRecord, Encounter
from app.models.consents import Consent
from app.models.core import User
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.services.booking import consultant_is_bookable
from app.services.notifications import enqueue_event


def _has_active_treatment_consent(db: Session, user_id) -> bool:
    return (
        db.execute(
            select(Consent.id).where(
                Consent.user_id == user_id,
                Consent.kind == "treatment",
                Consent.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        is not None
    )


def _system_admin_ids(db: Session) -> list:
    return list(
        db.execute(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(
                RolePermission, RolePermission.role_id == Role.id
            )
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                Role.name == "system_admin",
                User.status == "active",
                Permission.code == "encounters.manage",
            )
            .distinct()
        )
        .scalars()
        .all()
    )


def fulfill_paid_appointment(db: Session, *, appointment: Appointment) -> dict:
    """Auto-create clinical record and encounter for a just-paid appointment.

    Returns {"record_created": bool, "encounter_created": bool, "reason": str|None}.
    NEVER commits - the caller owns the transaction.
    """
    result = {"record_created": False, "encounter_created": False, "reason": None}

    if not _has_active_treatment_consent(db, appointment.user_id):
        enqueue_event(
            db,
            user_id=appointment.user_id,
            event_type="consent.required",
            payload={"appointment_id": str(appointment.id)},
        )
        result["reason"] = "consent_required"
        return result

    record = db.execute(
        select(ClinicalRecord).where(ClinicalRecord.user_id == appointment.user_id)
    ).scalar_one_or_none()
    if record is None:
        record = ClinicalRecord(user_id=appointment.user_id)
        db.add(record)
        db.flush()
        result["record_created"] = True
        db.add(
            AccessEvent(
                actor_user_id=None,  # system automation
                subject_user_id=appointment.user_id,
                action="clinical.record.auto_create",
                allowed=True,
                resource_type="clinical_record",
                resource_id=record.id,
                detail={"appointment_id": str(appointment.id)},
            )
        )

    consultant = db.get(Consultant, appointment.consultant_id)
    if consultant is None or not consultant_is_bookable(db, consultant):
        payload = {
            "appointment_id": str(appointment.id),
            "consultant_id": str(appointment.consultant_id),
        }
        for admin_id in _system_admin_ids(db):
            enqueue_event(
                db,
                user_id=admin_id,
                event_type="encounter.auto_create_failed",
                payload=payload,
            )
        result["reason"] = "consultant_not_eligible"
        return result

    existing = db.execute(
        select(Encounter).where(Encounter.appointment_id == appointment.id)
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            Encounter(
                record_id=record.id,
                consultant_id=appointment.consultant_id,
                appointment_id=appointment.id,
                start_at=appointment.start_at,
                end_at=appointment.end_at,
                status="scheduled",
            )
        )
        result["encounter_created"] = True
    return result
