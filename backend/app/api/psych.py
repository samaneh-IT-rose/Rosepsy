"""Psychology tests API (B37, Release 4).

Endpoints (prefix /api/v1):
- management: /psych-tests, /psych-test-versions/{id}/questions|interpretation-rules|
  approve|publish  (psych.manage + psych.review for approval)
- catalog: GET /psych-tests, GET /psych-tests/{id}
- attempts: POST /psych-tests/{id}/attempts · POST /psych-attempts/{id}/consent|
  answers|submit|abandon · GET /psych-attempts/{id}/questions
- results: GET /me/psych-results (owner-only) · GET /psych-attempts (reviewer queue)
  · POST /psych-attempts/{id}/review (psych.review)
Every result read writes an audit.access_events row (B41 governance).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import Profile, User
from app.models.psych import (
    PsychAnswer,
    PsychAttempt,
    PsychInterpretationRule,
    PsychQuestion,
    PsychTest,
    PsychTestVersion,
)
from app.services import psych as svc
from app.services.authz import write_audit

router = APIRouter(tags=["psych"])


# ─────────────────────────────── schemas ───────────────────────────────


class OptionIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    score: int = Field(ge=0, le=100)


class TestIn(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9\-]+$")
    title: str = Field(min_length=3, max_length=200)
    purpose: str | None = Field(default=None, max_length=1000)
    target_population: str | None = Field(default=None, max_length=300)
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    consent_kind: str = Field(default="psych_test", max_length=40)
    scientific_doc: str | None = Field(default=None, max_length=300)


class TestPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    purpose: str | None = Field(default=None, max_length=1000)
    target_population: str | None = Field(default=None, max_length=300)
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    scientific_doc: str | None = Field(default=None, max_length=300)


class VersionIn(BaseModel):
    scale_label: str = Field(min_length=2, max_length=120)


class QuestionIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    options: list[OptionIn] = Field(min_length=2, max_length=8)
    weight: int = Field(default=1, ge=1)
    position: int = Field(default=1, ge=1)


class RuleIn(BaseModel):
    min_score: int = Field(ge=0)
    max_score: int = Field(ge=0)
    title: str = Field(min_length=2, max_length=200)
    guidance: str = Field(min_length=5, max_length=2000)


class AnswersIn(BaseModel):
    answers: list[dict] = Field(min_length=1)


class ReviewIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


# ─────────────────────────────── serializers ───────────────────────────────


def _test_data(t: PsychTest, with_meta: bool = False) -> dict:
    data = {
        "id": str(t.id),
        "code": t.code,
        "title": t.title,
        "purpose": t.purpose,
        "target_population": t.target_population,
        "age_min": t.age_min,
        "age_max": t.age_max,
        "status": t.status,
        "scientific_doc": t.scientific_doc,
    }
    if with_meta:
        data["consent_kind"] = t.consent_kind
        data["created_at"] = t.created_at.isoformat()
    return data


def _version_data(v: PsychTestVersion) -> dict:
    return {
        "id": str(v.id),
        "test_id": str(v.test_id),
        "version": v.version,
        "scale_label": v.scale_label,
        "scoring_method": v.scoring_method,
        "status": v.status,
        "approved_at": v.approved_at.isoformat() if v.approved_at else None,
        "published_at": v.published_at.isoformat() if v.published_at else None,
    }


def _attempt_data(a: PsychAttempt, with_result: bool = False) -> dict:
    data = {
        "id": str(a.id),
        "test_id": str(a.test_id),
        "version_id": str(a.version_id),
        "status": a.status,
        "started_at": a.started_at.isoformat(),
    }
    if with_result:
        data.update(
            {
                "raw_score": a.raw_score,
                "rule_id": str(a.rule_id) if a.rule_id else None,
                "interpretation_title": a.interpretation_title,
                "interpretation_text": a.interpretation_text,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
                "review_note": a.review_note,
            }
        )
    return data


def _get_test(db: Session, test_id) -> PsychTest | None:
    tid = _uuid(test_id)
    return db.get(PsychTest, tid) if tid else None


def _get_attempt(db: Session, attempt_id) -> PsychAttempt | None:
    aid = _uuid(attempt_id)
    return db.get(PsychAttempt, aid) if aid else None


def _uuid(value) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


# ─────────────────────────────── management (psych.manage) ───────────────────────────────


@router.post("/psych-tests", status_code=201)
def create_test(
    body: TestIn,
    user: User = Depends(require_permission("psych.manage")),
    db: Session = Depends(get_db),
):
    if db.execute(select(PsychTest.id).where(PsychTest.code == body.code)).scalar_one_or_none():
        return error_response("PSYCH_CODE_EXISTS", "این کد تست قبلاً ثبت شده است", 409)
    if body.age_min is not None and body.age_max is not None and body.age_min > body.age_max:
        return error_response("AGE_RANGE_INVALID", "بازه سنی نامعتبر است", 422)
    t = PsychTest(
        code=body.code,
        title=body.title,
        purpose=body.purpose,
        target_population=body.target_population,
        age_min=body.age_min,
        age_max=body.age_max,
        consent_kind=body.consent_kind,
        scientific_doc=body.scientific_doc,
    )
    db.add(t)
    db.flush()
    write_audit(
        db,
        actor_user_id=user.id,
        action="psych.test_created",
        outcome="allowed",
        resource_type="psych_test",
        resource_id=t.id,
    )
    db.commit()
    return envelope(data=_test_data(t, with_meta=True))


@router.patch("/psych-tests/{test_id}")
def patch_test(
    test_id: uuid.UUID,
    body: TestPatch,
    user: User = Depends(require_permission("psych.manage")),
    db: Session = Depends(get_db),
):
    t = db.get(PsychTest, test_id)
    if t is None:
        return error_response("PSYCH_TEST_NOT_FOUND", "تست یافت نشد", 404)
    for field in ("title", "purpose", "target_population", "age_min", "age_max", "scientific_doc"):
        value = getattr(body, field)
        if value is not None:
            setattr(t, field, value)
    db.commit()
    return envelope(data=_test_data(t, with_meta=True))


@router.post("/psych-tests/{test_id}/versions", status_code=201)
def create_version(
    test_id: uuid.UUID,
    body: VersionIn,
    user: User = Depends(require_permission("psych.manage")),
    db: Session = Depends(get_db),
):
    t = db.get(PsychTest, test_id)
    if t is None:
        return error_response("PSYCH_TEST_NOT_FOUND", "تست یافت نشد", 404)
    last = db.execute(
        select(PsychTestVersion.version)
        .where(PsychTestVersion.test_id == t.id)
        .order_by(PsychTestVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    v = PsychTestVersion(test_id=t.id, version=(last or 0) + 1, scale_label=body.scale_label)
    db.add(v)
    db.flush()
    db.commit()
    return envelope(data=_version_data(v))


@router.post("/psych-test-versions/{version_id}/questions", status_code=201)
def add_question(
    version_id: uuid.UUID,
    body: QuestionIn,
    user: User = Depends(require_permission("psych.manage")),
    db: Session = Depends(get_db),
):
    v = db.get(PsychTestVersion, version_id)
    if v is None:
        return error_response("PSYCH_VERSION_NOT_FOUND", "نسخه یافت نشد", 404)
    if v.status != "draft":
        return error_response(
            "VERSION_IMMUTABLE", "نسخه منتشرشده/تأییدشده تغییرناپذیر است؛ نسخه جدید بسازید", 409
        )
    q = PsychQuestion(
        version_id=v.id,
        text=body.text,
        options=[o.model_dump() for o in body.options],
        weight=body.weight,
        position=body.position,
    )
    db.add(q)
    db.flush()
    db.commit()
    return envelope(data={"id": str(q.id), "position": q.position, "options_count": len(q.options)})


@router.post("/psych-test-versions/{version_id}/interpretation-rules", status_code=201)
def add_rule(
    version_id: uuid.UUID,
    body: RuleIn,
    user: User = Depends(require_permission("psych.manage")),
    db: Session = Depends(get_db),
):
    v = db.get(PsychTestVersion, version_id)
    if v is None:
        return error_response("PSYCH_VERSION_NOT_FOUND", "نسخه یافت نشد", 404)
    if v.status != "draft":
        return error_response("VERSION_IMMUTABLE", "نسخه تأییدشده تغییرناپذیر است", 409)
    if body.min_score > body.max_score:
        return error_response("RULE_BAND_INVALID", "بازه نمره قاعده نامعتبر است", 422)
    r = PsychInterpretationRule(
        version_id=v.id,
        min_score=body.min_score,
        max_score=body.max_score,
        title=body.title,
        guidance=body.guidance,
    )
    db.add(r)
    db.flush()
    db.commit()
    return envelope(data={"id": str(r.id), "status": r.status})


@router.post("/psych-test-versions/{version_id}/approve")
def approve_version(
    version_id: uuid.UUID,
    user: User = Depends(require_permission("psych.review")),
    db: Session = Depends(get_db),
):
    """Scientific approval (ناظر علمی): version + all its interpretation rules."""
    v = db.get(PsychTestVersion, version_id)
    if v is None:
        return error_response("PSYCH_VERSION_NOT_FOUND", "نسخه یافت نشد", 404)
    if v.status not in ("draft", "approved"):
        return error_response("VERSION_IMMUTABLE", "نسخه منتشرشده تغییرناپذیر است", 409)
    qcount = len(
        db.execute(select(PsychQuestion.id).where(PsychQuestion.version_id == v.id)).scalars().all()
    )
    if qcount == 0:
        return error_response("NO_QUESTIONS", "نسخه بدون سؤال قابل تأیید نیست", 422)
    rules = (
        db.execute(
            select(PsychInterpretationRule).where(PsychInterpretationRule.version_id == v.id)
        )
        .scalars()
        .all()
    )
    if not rules:
        return error_response(
            "NO_INTERPRETATION_RULES", "بدون قاعده تفسیر مصوب، انتشار ممنوع است", 422
        )
    now = datetime.now(UTC)
    v.status = "approved"
    v.approved_by = user.id
    v.approved_at = now
    for r in rules:
        r.status = "approved"
        r.approved_by = user.id
        r.approved_at = now
    write_audit(
        db,
        actor_user_id=user.id,
        action="psych.version_approved",
        outcome="allowed",
        resource_type="psych_test_version",
        resource_id=v.id,
        detail={"rules": len(rules), "questions": qcount},
    )
    db.commit()
    return envelope(data=_version_data(v))


@router.post("/psych-test-versions/{version_id}/publish")
def publish_version(
    version_id: uuid.UUID,
    user: User = Depends(require_permission("psych.manage")),
    db: Session = Depends(get_db),
):
    """انتشار فقط پس از تأیید علمی (approved). One published version per test."""
    v = db.get(PsychTestVersion, version_id)
    if v is None:
        return error_response("PSYCH_VERSION_NOT_FOUND", "نسخه یافت نشد", 404)
    if v.status != "approved":
        return error_response(
            "SCIENTIFIC_APPROVAL_REQUIRED",
            "انتشار تنها پس از تأیید علمی ناظر مجاز است",
            409,
        )
    t = db.get(PsychTest, v.test_id)
    previous = (
        db.execute(
            select(PsychTestVersion).where(
                PsychTestVersion.test_id == t.id,
                PsychTestVersion.status == "published",
            )
        )
        .scalars()
        .all()
    )
    for p in previous:
        p.status = "archived"
    v.status = "published"
    v.published_at = datetime.now(UTC)
    if t.status != "published":
        t.status = "published"
    write_audit(
        db,
        actor_user_id=user.id,
        action="psych.version_published",
        outcome="allowed",
        resource_type="psych_test_version",
        resource_id=v.id,
        detail={"test": t.code, "version": v.version, "archived": len(previous)},
    )
    db.commit()
    return envelope(data=_version_data(v))


@router.get("/psych-tests")
def list_tests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(
            select(PsychTest).where(PsychTest.status == "published").order_by(PsychTest.title)
        )
        .scalars()
        .all()
    )
    return envelope(data=[_test_data(t) for t in rows])


@router.get("/psych-tests/{test_id}")
def get_test(
    test_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(PsychTest, test_id)
    if t is None or t.status != "published":
        return error_response("PSYCH_TEST_NOT_FOUND", "تست یافت نشد", 404)
    v = svc.published_version(db, t.id)
    return envelope(data={**_test_data(t), "published_version": _version_data(v) if v else None})


# ─────────────────────────────── attempts (user) ───────────────────────────────


@router.post("/psych-tests/{test_id}/attempts", status_code=201)
def start_attempt(
    test_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(PsychTest, test_id)
    if t is None or t.status != "published":
        return error_response("PSYCH_TEST_NOT_FOUND", "تست یافت نشد یا منتشر نشده است", 404)
    profile = db.execute(select(Profile).where(Profile.user_id == user.id)).scalar_one_or_none()
    if not svc.age_gate_ok(t, profile):
        return error_response("AGE_RESTRICTION", "این آزمون برای گروه سنی شما مناسب نیست", 403)
    try:
        attempt = svc.start_attempt(db, test=t, user_id=user.id)
    except LookupError:
        return error_response("NO_PUBLISHED_VERSION", "نسخه منتشرشده‌ای وجود ندارد", 409)
    except PermissionError as exc:
        if str(exc) == "ATTEMPT_IN_PROGRESS":
            return error_response(
                "ATTEMPT_IN_PROGRESS", "یک اجرای ناتمام برای این آزمون دارید", 409
            )
        raise
    db.commit()
    return envelope(data=_attempt_data(attempt))


@router.post("/psych-attempts/{attempt_id}/consent")
def consent_attempt(
    attempt_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_attempt(db, attempt_id)
    if a is None or a.user_id != user.id:
        return error_response("PSYCH_ATTEMPT_NOT_FOUND", "اجرای آزمون یافت نشد", 404)
    try:
        a = svc.consent_attempt(db, a, ip=request.client.host if request.client else None)
    except PermissionError as exc:
        if str(exc) == "INVALID_STATE":
            return error_response("INVALID_STATE", "وضعیت اجرا اجازه ثبت رضایت نمی‌دهد", 409)
        return error_response(
            "CONSENT_REQUIRED",
            "برای ادامه، رضایت‌نامه معتبر آزمون لازم است (رضایت پیش از اجرا)",
            403,
        )
    db.commit()
    return envelope(data=_attempt_data(a))


@router.get("/psych-attempts/{attempt_id}/questions")
def attempt_questions(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Snapshot questions of the attempt's frozen version — option scores hidden."""
    a = _get_attempt(db, attempt_id)
    if a is None or not svc.can_view_attempt(db, a, user.id):
        return error_response("PSYCH_ATTEMPT_NOT_FOUND", "اجرای آزمون یافت نشد", 404)
    if a.status in ("abandoned",):
        return error_response("ATTEMPT_ABANDONED", "این اجرا رها شده است", 409)
    if a.status == "started":
        return error_response("CONSENT_REQUIRED", "نمایش سؤال‌ها پس از ثبت رضایت ممکن است", 403)
    questions = (
        db.execute(
            select(PsychQuestion)
            .where(PsychQuestion.version_id == a.version_id)
            .order_by(PsychQuestion.position)
        )
        .scalars()
        .all()
    )
    answered = {
        str(row.question_id): row.option_index
        for row in db.execute(select(PsychAnswer).where(PsychAnswer.attempt_id == a.id)).scalars()
    }
    return envelope(
        data={
            "attempt": _attempt_data(a),
            "questions": [
                {
                    "id": str(q.id),
                    "text": q.text,
                    "position": q.position,
                    "options": [
                        {"label": o.get("label")}
                        for o in q.options  # scores hidden
                    ],
                    "answered_index": answered.get(str(q.id)),
                }
                for q in questions
            ],
        }
    )


@router.post("/psych-attempts/{attempt_id}/answers")
def save_answers(
    attempt_id: uuid.UUID,
    body: AnswersIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_attempt(db, attempt_id)
    if a is None or a.user_id != user.id:
        return error_response("PSYCH_ATTEMPT_NOT_FOUND", "اجرای آزمون یافت نشد", 404)
    try:
        a = svc.save_answers(db, a, body.answers)
    except LookupError:
        return error_response("QUESTION_NOT_IN_VERSION", "سؤال خارج از نسخه ثابت است", 422)
    except ValueError:
        return error_response("OPTION_INDEX_INVALID", "گزینه انتخابی نامعتبر است", 422)
    except PermissionError:
        return error_response("INVALID_STATE", "وضعیت اجرا اجازه ثبت پاسخ نمی‌دهد", 409)
    db.commit()
    return envelope(data=_attempt_data(a))


@router.post("/psych-attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_attempt(db, attempt_id)
    if a is None or a.user_id != user.id:
        return error_response("PSYCH_ATTEMPT_NOT_FOUND", "اجرای آزمون یافت نشد", 404)
    try:
        a = svc.submit_attempt(db, a)
    except PermissionError as exc:
        if str(exc) == "ATTEMPT_ALREADY_SCORED":
            return error_response("ATTEMPT_ALREADY_SCORED", "این اجرا قبلاً نمره‌گذاری شده است", 409)
        return error_response("INVALID_STATE", "ارسال نتیجه در وضعیت فعلی مجاز نیست", 409)
    svc.log_result_access(
        db,
        actor_user_id=user.id,
        subject_user_id=user.id,
        attempt=a,
        allowed=True,
    )
    db.commit()
    return envelope(data=_attempt_data(a, with_result=True))


@router.post("/psych-attempts/{attempt_id}/abandon")
def abandon_attempt(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_attempt(db, attempt_id)
    if a is None or a.user_id != user.id:
        return error_response("PSYCH_ATTEMPT_NOT_FOUND", "اجرای آزمون یافت نشد", 404)
    try:
        a = svc.abandon_attempt(db, a)
    except PermissionError:
        return error_response("INVALID_STATE", "این اجرا قابل رها کردن نیست", 409)
    db.commit()
    return envelope(data=_attempt_data(a))


@router.get("/me/psych-results")
def my_results(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """نتایج من — strictly the caller's own rows (نتیجه دیگران دیده نشود)."""
    rows = (
        db.execute(
            select(PsychAttempt)
            .where(
                PsychAttempt.user_id == user.id,
                PsychAttempt.status.in_(("scored", "reviewed")),
            )
            .order_by(PsychAttempt.scored_at.desc())
        )
        .scalars()
        .all()
    )
    for a in rows:
        svc.log_result_access(
            db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            attempt=a,
            allowed=True,
        )
    db.commit()
    return envelope(data=[_attempt_data(a, with_result=True) for a in rows])


@router.get("/psych-attempts")
def review_queue(
    status: str | None = None,
    user: User = Depends(require_permission("psych.review")),
    db: Session = Depends(get_db),
):
    """Reviewer queue (ناظر علمی) — access to others' results is logged."""
    q = select(PsychAttempt).order_by(PsychAttempt.scored_at.desc())
    if status:
        q = q.where(PsychAttempt.status == status)
    rows = db.execute(q.limit(200)).scalars().all()
    for a in rows:
        svc.log_result_access(
            db,
            actor_user_id=user.id,
            subject_user_id=a.user_id,
            attempt=a,
            allowed=True,
        )
    db.commit()
    return envelope(data=[_attempt_data(a, with_result=True) for a in rows])


@router.post("/psych-attempts/{attempt_id}/review")
def review_attempt(
    attempt_id: uuid.UUID,
    body: ReviewIn,
    user: User = Depends(require_permission("psych.review")),
    db: Session = Depends(get_db),
):
    a = _get_attempt(db, attempt_id)
    if a is None:
        return error_response("PSYCH_ATTEMPT_NOT_FOUND", "اجرای آزمون یافت نشد", 404)
    try:
        a = svc.review_attempt(db, a, reviewer_id=user.id, note=body.note)
    except PermissionError:
        return error_response("INVALID_STATE", "فقط اجرای نمره‌گذاری‌شده قابل بازبینی است", 409)
    db.commit()
    return envelope(data=_attempt_data(a, with_result=True))
