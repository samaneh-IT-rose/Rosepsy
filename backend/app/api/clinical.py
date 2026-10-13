import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.clinical import (
    ClinicalRecord,
    Encounter,
    EncounterAmendment,
    EncounterNote,
    Questionnaire,
    QuestionnaireVersion,
    Submission,
)
from app.models.consents import Consent
from app.models.core import User
from app.models.files import File
from app.services.authz import has_permission, write_access_event
from app.services.clinical import assert_record_read, user_is_consultant

router = APIRouter(tags=["clinical"])


# ---------- helpers ----------


def _active_consent(db: Session, user_id, kind: str) -> bool:
    return (
        db.execute(
            select(Consent.id).where(
                Consent.user_id == user_id,
                Consent.kind == kind,
                Consent.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        is not None
    )


def _get_record(db: Session, record_id: uuid.UUID) -> ClinicalRecord | None:
    return db.get(ClinicalRecord, record_id)


def _can_read(db: Session, user: User, record: ClinicalRecord, request: Request) -> bool:
    """Owner or authorized consultant; ALWAYS writes an access event (B13)."""
    if record.user_id == user.id:
        write_access_event(
            db,
            actor_user_id=user.id,
            subject_user_id=record.user_id,
            action="clinical.record.read",
            allowed=True,
            resource_type="clinical_record",
            resource_id=record.id,
            request_id=request_id_var.get(),
            ip=request.client.host if request.client else None,
            detail={"reason": "owner"},
        )
        return True
    allowed, _err = assert_record_read(
        db, user=user, record_id=record.id,
        request_ip=request.client.host if request.client else None,
    )
    return allowed


def _record_data(db: Session, r: ClinicalRecord) -> dict:
    return {
        "id": str(r.id),
        "user_id": str(r.user_id),
        "summary": r.summary,
        "risk_level": r.risk_level,
        "created_at": r.created_at.isoformat(),
    }


def _own_record(db: Session, user: User) -> ClinicalRecord | None:
    return db.execute(
        select(ClinicalRecord).where(ClinicalRecord.user_id == user.id)
    ).scalar_one_or_none()


# ---------- B13: records ----------


class RecordIn(BaseModel):
    user_id: uuid.UUID
    summary: str | None = Field(default=None, max_length=1000)
    risk_level: str = Field(default="unknown", pattern=r"^(low|medium|high|unknown)$")


@router.post("/clinical-records", status_code=201)
def create_record(
    body: RecordIn,
    request: Request,
    user: User = Depends(require_permission("records.manage")),
    db: Session = Depends(get_db),
):
    """Create a record - only with an active treatment consent (spec + BPMN 03)."""
    target = db.get(User, body.user_id)
    if target is None:
        return error_response("USER_NOT_FOUND", "کاربر یافت نشد", 404)
    if not _active_consent(db, target.id, "treatment"):
        return error_response(
            "CONSENT_REQUIRED",
            "بدون رضایت فعال درمان، پرونده ساخته نمی‌شود",
            409,
        )
    dup = db.execute(
        select(ClinicalRecord).where(ClinicalRecord.user_id == body.user_id)
    ).scalar_one_or_none()
    if dup is not None:
        return error_response(
            "RECORD_EXISTS", "پرونده برای این کاربر وجود دارد", 409,
            details={"record_id": str(dup.id)},
        )
    record = ClinicalRecord(
        user_id=body.user_id, summary=body.summary, risk_level=body.risk_level,
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    write_access_event(
        db,
        actor_user_id=user.id,
        subject_user_id=target.id,
        action="clinical.record.create",
        allowed=True,
        resource_type="clinical_record",
        resource_id=record.id,
        request_id=request_id_var.get(),
    )
    return envelope(data=_record_data(db, record))


@router.get("/clinical-records/me")
def my_record(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _own_record(db, user)
    if record is None:
        return error_response("RECORD_NOT_FOUND", "پرونده‌ای برای شما ثبت نشده است", 404)
    _can_read(db, user, record, request)  # owner read -> allowed + event
    return envelope(data=_record_data(db, record))


@router.get("/clinical-records/{record_id}")
def get_record(
    record_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _get_record(db, record_id)
    if record is None:
        return error_response("RECORD_NOT_FOUND", "پرونده یافت نشد", 404)
    if not _can_read(db, user, record, request):
        return error_response("FORBIDDEN", "دسترسی به این پرونده مجاز نیست", 403)
    return envelope(data=_record_data(db, record))


class RecordFileIn(BaseModel):
    file_id: uuid.UUID


@router.post("/clinical-records/{record_id}/files", status_code=201)
def attach_file(
    record_id: uuid.UUID,
    body: RecordFileIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner attaches their own clean file to their own record."""
    record = _get_record(db, record_id)
    if record is None or record.user_id != user.id:
        return error_response("RECORD_NOT_FOUND", "پرونده یافت نشد", 404)
    f = db.get(File, body.file_id)
    if f is None or f.owner_user_id != user.id:
        return error_response("FILE_NOT_FOUND", "فایل یافت نشد", 404)
    if f.status != "clean":
        return error_response("FILE_NOT_READY", "فقط فایل پاک قابل پیوست است", 409)

    from app.models.clinical import RecordFile

    link = RecordFile(
        record_id=record.id, file_id=f.id, attached_by=user.id
    )
    db.add(link)
    db.commit()
    write_access_event(
        db,
        actor_user_id=user.id,
        subject_user_id=user.id,
        action="clinical.record.attach_file",
        allowed=True,
        resource_type="clinical_record",
        resource_id=record.id,
        request_id=request_id_var.get(),
        detail={"file_id": str(f.id)},
    )
    return envelope(data={"id": str(link.id), "file_id": str(f.id)})


# ---------- B14: questionnaires ----------


class QuestionnaireIn(BaseModel):
    title_fa: str = Field(min_length=2, max_length=150)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")


class VersionIn(BaseModel):
    form_schema: dict = Field(alias="schema_json")


class SubmissionIn(BaseModel):
    version_id: uuid.UUID
    answers: dict = Field(min_length=1)


@router.post("/questionnaires", status_code=201)
def create_questionnaire(
    body: QuestionnaireIn,
    user: User = Depends(require_permission("questionnaires.manage")),
    db: Session = Depends(get_db),
):
    dup = db.execute(
        select(Questionnaire).where(Questionnaire.slug == body.slug)
    ).scalar_one_or_none()
    if dup is not None:
        return error_response("DUPLICATE_SLUG", "این slug قبلاً ثبت شده است", 409)
    q = Questionnaire(title_fa=body.title_fa.strip(), slug=body.slug, created_by=user.id)
    db.add(q)
    db.commit()
    return envelope(data={"id": str(q.id), "slug": q.slug})


@router.post("/questionnaires/{questionnaire_id}/versions", status_code=201)
def create_questionnaire_version(
    questionnaire_id: uuid.UUID,
    body: VersionIn,
    user: User = Depends(require_permission("questionnaires.manage")),
    db: Session = Depends(get_db),
):
    q = db.get(Questionnaire, questionnaire_id)
    if q is None:
        return error_response("QUESTIONNAIRE_NOT_FOUND", "پرسشنامه یافت نشد", 404)
    latest = db.execute(
        select(QuestionnaireVersion)
        .where(QuestionnaireVersion.questionnaire_id == questionnaire_id)
        .order_by(QuestionnaireVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    v = QuestionnaireVersion(
        questionnaire_id=questionnaire_id,
        version=(latest.version + 1) if latest else 1,
        schema_json=body.form_schema,
        created_by=user.id,
    )
    db.add(v)
    db.commit()
    return envelope(data={"id": str(v.id), "version": v.version})


@router.post("/submissions", status_code=201)
def submit_answers(
    body: SubmissionIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Answers locked to the submitted version; record owner only (B14)."""
    record = _own_record(db, user)
    if record is None:
        return error_response("RECORD_NOT_FOUND", "پرونده‌ای برای شما ثبت نشده است", 404)
    v = db.get(QuestionnaireVersion, body.version_id)
    if v is None:
        return error_response("VERSION_NOT_FOUND", "نسخه پرسشنامه یافت نشد", 404)
    sub = Submission(
        record_id=record.id,
        version_id=v.id,
        answers=body.answers,
        submitted_by=user.id,
    )
    db.add(sub)
    db.commit()
    write_access_event(
        db,
        actor_user_id=user.id,
        subject_user_id=user.id,
        action="clinical.submission.create",
        allowed=True,
        resource_type="submission",
        resource_id=sub.id,
        request_id=request_id_var.get(),
        detail={"questionnaire_version": v.version},
    )
    return envelope(data={"id": str(sub.id), "version_id": str(v.id)})


@router.get("/clinical-records/{record_id}/submissions")
def record_submissions(
    record_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _get_record(db, record_id)
    if record is None:
        return error_response("RECORD_NOT_FOUND", "پرونده یافت نشد", 404)
    if not _can_read(db, user, record, request):
        return error_response("FORBIDDEN", "دسترسی مجاز نیست", 403)
    rows = (
        db.execute(
            select(Submission)
            .where(Submission.record_id == record_id)
            .order_by(Submission.created_at.desc())
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(s.id),
                "version_id": str(s.version_id),
                "answers": s.answers,
                "created_at": s.created_at.isoformat(),
            }
            for s in rows
        ]
    )


# ---------- B15/B16: encounters and notes ----------




@router.get("/encounters/mine")
def my_encounters(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sessions of the logged-in consultant (B15/B16 readiness)."""
    cons = user_is_consultant(db, user)
    if cons is None:
        return error_response("NOT_A_CONSULTANT", "کاربر جاری مشاور نیست", 403)
    rows = (
        db.execute(
            select(Encounter)
            .where(Encounter.consultant_id == cons.id)
            .order_by(Encounter.start_at.desc())
        )
        .scalars()
        .all()
    )
    return envelope(data=[_encounter_view(db, e) for e in rows])


@router.get("/encounters/{encounter_id}/record")
def encounter_record(
    encounter_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Consultant reads the client record through the session link (B13)."""
    e, err = _encounter_or_404(db, encounter_id)
    if err:
        return err
    cons = user_is_consultant(db, user)
    if cons is None or cons.id != e.consultant_id:
        return error_response("FORBIDDEN", "فقط مشاور جلسه دسترسی دارد", 403)
    record = _get_record(db, e.record_id)
    if record is None:
        return error_response("RECORD_NOT_FOUND", "پرونده یافت نشد", 404)
    write_access_event(
        db,
        actor_user_id=user.id,
        subject_user_id=record.user_id,
        action="clinical.record.read",
        allowed=True,
        resource_type="clinical_record",
        resource_id=record.id,
        request_id=request_id_var.get(),
        detail={"via": "encounter"},
    )
    return envelope(data=_record_data(db, record))
class EncounterIn(BaseModel):
    record_id: uuid.UUID
    consultant_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    appointment_id: uuid.UUID | None = None


class StatusIn(BaseModel):
    status: str = Field(pattern=r"^(in_progress|completed|cancelled|no_show)$")


class NoteIn(BaseModel):
    body: str = Field(min_length=2, max_length=5000)


class AmendmentIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)
    body: str = Field(min_length=2, max_length=5000)


def _encounter_or_404(db: Session, encounter_id: uuid.UUID):
    e = db.get(Encounter, encounter_id)
    if e is None:
        return None, error_response("ENCOUNTER_NOT_FOUND", "جلسه یافت نشد", 404)
    return e, None


def _encounter_view(db: Session, e: Encounter) -> dict:
    return {
        "id": str(e.id),
        "record_id": str(e.record_id),
        "consultant_id": str(e.consultant_id),
        "start_at": e.start_at.isoformat(),
        "end_at": e.end_at.isoformat(),
        "status": e.status,
    }


@router.post("/encounters", status_code=201)
def create_encounter(
    body: EncounterIn,
    user: User = Depends(require_permission("encounters.manage")),
    db: Session = Depends(get_db),
):
    record = _get_record(db, body.record_id)
    if record is None:
        return error_response("RECORD_NOT_FOUND", "پرونده یافت نشد", 404)
    if body.end_at <= body.start_at:
        return error_response("INVALID_RANGE", "پایان جلسه باید بعد از شروع باشد", 422)
    e = Encounter(
        record_id=body.record_id,
        consultant_id=body.consultant_id,
        appointment_id=body.appointment_id,
        start_at=body.start_at,
        end_at=body.end_at,
        created_by=user.id,
    )
    db.add(e)
    db.commit()
    return envelope(data=_encounter_view(db, e))


@router.post("/encounters/{encounter_id}/status")
def set_encounter_status(
    encounter_id: uuid.UUID,
    body: StatusIn,
    user: User = Depends(require_permission("encounters.manage")),
    db: Session = Depends(get_db),
):
    """Status monitoring only - no clinical content here (B16 separation)."""
    e, err = _encounter_or_404(db, encounter_id)
    if err:
        return err
    allowed = {
        "scheduled": {"in_progress", "cancelled", "no_show"},
        "in_progress": {"completed", "cancelled"},
    }
    if body.status not in allowed.get(e.status, set()):
        return error_response(
            "INVALID_TRANSITION", f"گذار از {e.status} به {body.status} مجاز نیست", 409
        )
    e.status = body.status
    db.commit()
    return envelope(data=_encounter_view(db, e))


@router.get("/encounters/{encounter_id}")
def get_encounter(
    encounter_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Status view: record owner, session consultant, or encounters.manage."""
    e, err = _encounter_or_404(db, encounter_id)
    if err:
        return err
    record = _get_record(db, e.record_id)
    cons = user_is_consultant(db, user)
    if not (
        (record and record.user_id == user.id)
        or (cons and cons.id == e.consultant_id)
        or has_permission(db, user.id, "encounters.manage")
    ):
        return error_response("FORBIDDEN", "دسترسی مجاز نیست", 403)
    return envelope(data=_encounter_view(db, e))


@router.post("/encounters/{encounter_id}/notes", status_code=201)
def add_note(
    encounter_id: uuid.UUID,
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Only the session consultant writes notes (B15)."""
    e, err = _encounter_or_404(db, encounter_id)
    if err:
        return err
    cons = user_is_consultant(db, user)
    if cons is None or cons.id != e.consultant_id:
        return error_response("FORBIDDEN", "فقط مشاور جلسه یادداشت ثبت می‌کند", 403)
    note = EncounterNote(encounter_id=e.id, author_id=user.id, body=body.body.strip())
    db.add(note)
    db.commit()
    write_access_event(
        db,
        actor_user_id=user.id,
        action="clinical.note.create",
        allowed=True,
        resource_type="encounter_note",
        resource_id=note.id,
        request_id=request_id_var.get(),
    )
    return envelope(data={"id": str(note.id), "confirmed": False})


@router.post("/notes/{note_id}/confirm")
def confirm_note(
    note_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.get(EncounterNote, note_id)
    if note is None:
        return error_response("NOTE_NOT_FOUND", "یادداشت یافت نشد", 404)
    cons = user_is_consultant(db, user)
    if cons is None or note.author_id != user.id:
        return error_response("FORBIDDEN", "فقط نویسنده یادداشت تأیید می‌کند", 403)
    if note.confirmed:
        return error_response("NOTE_ALREADY_CONFIRMED", "یادداشت قبلاً تأیید شده است", 409)
    note.confirmed = True
    db.commit()
    return envelope(data={"id": str(note.id), "confirmed": True})


@router.get("/encounters/{encounter_id}/notes")
def encounter_notes(
    encounter_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Notes are clinical content: consultant of the session or record owner."""
    e, err = _encounter_or_404(db, encounter_id)
    if err:
        return err
    record = _get_record(db, e.record_id)
    cons = user_is_consultant(db, user)
    if not (
        (record and record.user_id == user.id)
        or (cons and cons.id == e.consultant_id)
    ):
        return error_response("FORBIDDEN", "دسترسی مجاز نیست", 403)
    rows = (
        db.execute(
            select(EncounterNote)
            .where(EncounterNote.encounter_id == encounter_id)
            .order_by(EncounterNote.created_at)
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(n.id),
                "body": n.body,
                "confirmed": n.confirmed,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ]
    )


@router.post("/notes/{note_id}/amendments", status_code=201)
def amend_note(
    note_id: uuid.UUID,
    body: AmendmentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirmed notes are FROZEN; corrections append as amendments (B15)."""
    note = db.get(EncounterNote, note_id)
    if note is None:
        return error_response("NOTE_NOT_FOUND", "یادداشت یافت نشد", 404)
    if note.author_id != user.id:
        return error_response("FORBIDDEN", "فقط نویسنده اصلاحیه ثبت می‌کند", 403)
    if not note.confirmed:
        return error_response(
            "NOTE_NOT_CONFIRMED", "یادداشت تأییدنشده را مستقیم ویرایش کنید", 409
        )
    amendment = EncounterAmendment(
        note_id=note.id, author_id=user.id, reason=body.reason.strip(),
        body=body.body.strip(),
    )
    db.add(amendment)
    db.commit()
    write_access_event(
        db,
        actor_user_id=user.id,
        action="clinical.note.amend",
        allowed=True,
        resource_type="encounter_note",
        resource_id=note.id,
        request_id=request_id_var.get(),
    )
    return envelope(data={"id": str(amendment.id), "note_id": str(note.id)})


@router.patch("/notes/{note_id}")
def edit_unconfirmed_note(
    note_id: uuid.UUID,
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.get(EncounterNote, note_id)
    if note is None:
        return error_response("NOTE_NOT_FOUND", "یادداشت یافت نشد", 404)
    if note.author_id != user.id:
        return error_response("FORBIDDEN", "فقط نویسنده ویرایش می‌کند", 403)
    if note.confirmed:
        return error_response(
            "NOTE_CONFIRMED", "یادداشت تأییدشده تغییر نمی‌کند؛ اصلاحیه ثبت کنید", 409
        )
    note.body = body.body.strip()
    db.commit()
    return envelope(data={"id": str(note.id), "body": note.body})
