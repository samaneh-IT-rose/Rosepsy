"""Education service (B34-B36): enrollment, access, scoring, certificates."""

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.edu import (
    AccessGrant,
    Certificate,
    Course,
    CourseEnrollment,
    CourseExam,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    Lesson,
)
from app.services.authz import write_audit


def has_active_access(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    grant = db.execute(
        select(AccessGrant.id).where(
            AccessGrant.user_id == user_id,
            AccessGrant.course_id == course_id,
            AccessGrant.revoked_at.is_(None),
            (AccessGrant.expires_at.is_(None)) | (AccessGrant.expires_at >= datetime.now(UTC)),
        )
    ).scalar_one_or_none()
    return grant is not None


def get_or_create_enrollment(
    db: Session, *, user_id: uuid.UUID, course: Course, source: str, order_id=None
) -> CourseEnrollment:
    """Idempotent: one enrollment row per (user, course)."""
    enrollment = db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == user_id, CourseEnrollment.course_id == course.id
        )
    ).scalar_one_or_none()
    if enrollment is not None:
        return enrollment
    status = "active" if course.is_free else "pending_payment"
    enrollment = CourseEnrollment(
        user_id=user_id,
        course_id=course.id,
        status=status,
        source=source,
        order_id=order_id,
        activated_at=datetime.now(UTC) if course.is_free else None,
    )
    db.add(enrollment)
    db.flush()
    if course.is_free:
        grant_access(db, user_id=user_id, course_id=course.id, source="free")
    return enrollment


def grant_access(
    db: Session,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    source: str,
    order_id=None,
) -> AccessGrant:
    """Exactly one grant per (user, course) - duplicate requests never duplicate access."""
    grant = db.execute(
        select(AccessGrant).where(
            AccessGrant.user_id == user_id, AccessGrant.course_id == course_id
        )
    ).scalar_one_or_none()
    if grant is not None:
        if grant.revoked_at is not None:
            grant.revoked_at = None
            db.flush()
        return grant
    grant = AccessGrant(
        user_id=user_id, course_id=course_id, source=source, order_id=order_id
    )
    db.add(grant)
    db.flush()
    return grant


def fulfill_course_order(db: Session, order) -> dict:
    """Activate the pending enrollment of a paid course order (called in the
    payments callback transaction). Idempotent: activation happens once."""
    enrollment = db.execute(
        select(CourseEnrollment).where(CourseEnrollment.order_id == order.id)
    ).scalar_one_or_none()
    if enrollment is None:
        return {"activated": False, "reason": "enrollment_not_found"}
    if enrollment.status == "active":
        return {"activated": True, "already_active": True}
    enrollment.status = "active"
    enrollment.activated_at = datetime.now(UTC)
    grant_access(
        db,
        user_id=enrollment.user_id,
        course_id=enrollment.course_id,
        source="purchase",
        order_id=order.id,
    )
    write_audit(
        db,
        actor_user_id=enrollment.user_id,
        action="course.enrollment_activated",
        outcome="allowed",
        resource_type="course_enrollment",
        resource_id=enrollment.id,
        detail={"order_id": str(order.id)},
    )
    return {"activated": True, "already_active": False}


def score_attempt(db: Session, attempt: ExamAttempt, answers: list[dict]) -> ExamAttempt:
    """Server-side scoring (B36): client never sends scores."""
    exam = db.get(CourseExam, attempt.exam_id)
    questions = db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == attempt.exam_id)
    ).scalars().all()
    qmap = {q.id: q for q in questions}
    total_weight = sum(q.weight for q in questions) or 1

    by_qid = {}
    for a in answers:
        qid = a.get("question_id")
        if isinstance(qid, str):
            try:
                qid = uuid.UUID(qid)
            except ValueError:
                continue
        if qid in qmap and qid not in by_qid:
            by_qid[qid] = a.get("selected_index")

    earned = 0
    for qid, selected in by_qid.items():
        q = qmap[qid]
        correct = isinstance(selected, int) and selected == q.correct_index
        if correct:
            earned += q.weight
        db.add(
            ExamAnswer(
                attempt_id=attempt.id,
                question_id=qid,
                selected_index=selected if isinstance(selected, int) else -1,
                is_correct=correct,
            )
        )
    score = round(earned * 100 / total_weight)
    attempt.score = score
    attempt.status = "passed" if score >= exam.pass_score else "failed"
    attempt.submitted_at = datetime.now(UTC)
    db.flush()
    return attempt


def next_certificate_number(db: Session) -> str:
    seq = db.execute(
        select(func.count()).select_from(Certificate)
    ).scalar_one()
    year = datetime.now(UTC).year
    return f"CERT-{year}-{seq + 1:06d}"


def issue_certificate(db: Session, attempt: ExamAttempt, actor_user_id) -> Certificate:
    """Exactly one certificate per attempt; attempt must be passed."""
    existing = db.execute(
        select(Certificate).where(Certificate.exam_attempt_id == attempt.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    exam = db.get(CourseExam, attempt.exam_id)
    cert = Certificate(
        user_id=attempt.user_id,
        course_id=exam.course_id,
        exam_attempt_id=attempt.id,
        certificate_number=next_certificate_number(db),
        verification_code=secrets.token_hex(8),
    )
    db.add(cert)
    db.flush()
    # mark the enrollment completed on certificate issue
    enrollment = db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == attempt.user_id,
            CourseEnrollment.course_id == exam.course_id,
        )
    ).scalar_one_or_none()
    if enrollment is not None and enrollment.status == "active":
        enrollment.status = "completed"
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="certificate.issued",
        outcome="allowed",
        resource_type="certificate",
        resource_id=cert.id,
        detail={"number": cert.certificate_number},
    )
    return cert


def course_has_valid_lesson(db: Session, course_id: uuid.UUID) -> bool:
    """A course is publishable only with at least one lesson that has a file (B34)."""
    from app.models.edu import CourseModule

    return (
        db.execute(
            select(Lesson.id)
            .join(CourseModule, CourseModule.id == Lesson.module_id)
            .where(CourseModule.course_id == course_id, Lesson.file_id.is_not(None))
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )
