"""Psychology test service (B37): attempts, consent gate, scoring, review.

Key spec rules enforced here:
- consent BEFORE answering (server-side consent check, never client-side)
- answers/scores frozen to the attempt's version snapshot
- server-side scoring only; the client never sends scores
- interpretation only from approved rules of the same version; the scored
  attempt snapshots the rule text so it stays traceable to the مصوبه
- owner-only results; scientific reviewer reads are logged via access_events
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AccessEvent
from app.models.consents import Consent
from app.models.core import Profile
from app.models.psych import (
    PsychAnswer,
    PsychAttempt,
    PsychInterpretationRule,
    PsychQuestion,
    PsychTest,
    PsychTestVersion,
    user_age,
)
from app.services.authz import write_audit

ACTIVE_STATUSES = ("started", "consented", "in_progress")
TERMINAL_STATUSES = ("scored", "reviewed", "abandoned")


def has_active_consent(db: Session, user_id: uuid.UUID, kind: str) -> Consent | None:
    return db.execute(
        select(Consent).where(
            Consent.user_id == user_id,
            Consent.kind == kind,
            Consent.revoked_at.is_(None),
        )
    ).scalar_one_or_none()


def published_version(db: Session, test_id: uuid.UUID) -> PsychTestVersion | None:
    return db.execute(
        select(PsychTestVersion)
        .where(
            PsychTestVersion.test_id == test_id,
            PsychTestVersion.status == "published",
        )
        .order_by(PsychTestVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def age_gate_ok(test: PsychTest, profile: Profile | None) -> bool:
    """محدودیت سنی: reject when the profile age is outside the declared band."""
    if profile is None or profile.birth_date is None:
        return True  # no birth date recorded → cannot gate (recorded in audit by caller)
    age = user_age(profile.birth_date, date.today())
    if age is None:
        return True
    if test.age_min is not None and age < test.age_min:
        return False
    if test.age_max is not None and age > test.age_max:
        return False
    return True


def start_attempt(
    db: Session, *, test: PsychTest, user_id: uuid.UUID, ip: str | None = None
) -> PsychAttempt:
    """Create a `started` attempt bound to the current published version."""
    version = published_version(db, test.id)
    if version is None:
        raise LookupError("NO_PUBLISHED_VERSION")
    active = db.execute(
        select(PsychAttempt).where(
            PsychAttempt.user_id == user_id,
            PsychAttempt.test_id == test.id,
            PsychAttempt.status.in_(ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()
    if active is not None:
        raise PermissionError("ATTEMPT_IN_PROGRESS")
    attempt = PsychAttempt(test_id=test.id, user_id=user_id, version_id=version.id)
    db.add(attempt)
    db.flush()
    write_audit(
        db,
        actor_user_id=user_id,
        action="psych.attempt_started",
        outcome="allowed",
        resource_type="psych_attempt",
        resource_id=attempt.id,
        ip=ip,
        detail={"test": test.code, "version": version.version},
    )
    return attempt


def consent_attempt(db: Session, attempt: PsychAttempt, *, ip: str | None = None) -> PsychAttempt:
    """started → consented: requires an active consent of the test's kind."""
    if attempt.status != "started":
        raise PermissionError("INVALID_STATE")
    consent = has_active_consent(db, attempt.user_id, _test_kind(db, attempt.test_id))
    if consent is None:
        raise PermissionError("CONSENT_REQUIRED")
    attempt.status = "consented"
    attempt.consented_at = datetime.now(UTC)
    attempt.consent_id = consent.id
    db.flush()
    write_audit(
        db,
        actor_user_id=attempt.user_id,
        action="psych.attempt_consented",
        outcome="allowed",
        resource_type="psych_attempt",
        resource_id=attempt.id,
        ip=ip,
        detail={"consent_id": str(consent.id)},
    )
    return attempt


def save_answers(db: Session, attempt: PsychAttempt, answers: list[dict]) -> PsychAttempt:
    """Upsert answers while in flight; scores come from the frozen version."""
    if attempt.status not in ("consented", "in_progress"):
        raise PermissionError("INVALID_STATE")
    questions = _version_questions(db, attempt.version_id)
    qmap = {q.id: q for q in questions}
    known = {
        a.question_id: a
        for a in db.execute(
            select(PsychAnswer).where(PsychAnswer.attempt_id == attempt.id)
        ).scalars()
    }
    for a in answers:
        qid = _uuid(a.get("question_id"))
        if qid is None or qid not in qmap:
            raise LookupError("QUESTION_NOT_IN_VERSION")
        idx = a.get("option_index")
        q = qmap[qid]
        if not isinstance(idx, int) or idx < 0 or idx >= len(q.options):
            raise ValueError("OPTION_INDEX_INVALID")
        score = int(q.options[idx].get("score", 0))
        row = known.get(qid)
        if row is None:
            db.add(
                PsychAnswer(
                    attempt_id=attempt.id,
                    question_id=qid,
                    option_index=idx,
                    option_score=score,
                )
            )
        else:
            row.option_index = idx
            row.option_score = score
    attempt.status = "in_progress"
    db.flush()
    return attempt


def submit_attempt(db: Session, attempt: PsychAttempt) -> PsychAttempt:
    """Server-side scoring + approved interpretation; double submit is rejected."""
    if attempt.status in TERMINAL_STATUSES:
        raise PermissionError("ATTEMPT_ALREADY_SCORED")
    if attempt.status not in ("consented", "in_progress"):
        raise PermissionError("INVALID_STATE")
    answers = (
        db.execute(select(PsychAnswer).where(PsychAnswer.attempt_id == attempt.id)).scalars().all()
    )
    raw = sum(a.option_score for a in answers)
    rule = db.execute(
        select(PsychInterpretationRule)
        .where(
            PsychInterpretationRule.version_id == attempt.version_id,
            PsychInterpretationRule.status == "approved",
            PsychInterpretationRule.min_score <= raw,
            PsychInterpretationRule.max_score >= raw,
        )
        .limit(1)
    ).scalar_one_or_none()
    attempt.raw_score = raw
    attempt.submitted_at = datetime.now(UTC)
    attempt.scored_at = datetime.now(UTC)
    if rule is not None:
        attempt.rule_id = rule.id
        attempt.interpretation_title = rule.title
        attempt.interpretation_text = rule.guidance
    attempt.status = "scored"
    db.flush()
    write_audit(
        db,
        actor_user_id=attempt.user_id,
        action="psych.attempt_scored",
        outcome="allowed",
        resource_type="psych_attempt",
        resource_id=attempt.id,
        detail={"raw_score": raw, "rule_id": str(rule.id) if rule else None},
    )
    return attempt


def review_attempt(
    db: Session,
    attempt: PsychAttempt,
    *,
    reviewer_id: uuid.UUID,
    note: str | None,
) -> PsychAttempt:
    if attempt.status != "scored":
        raise PermissionError("INVALID_STATE")
    attempt.status = "reviewed"
    attempt.reviewed_by = reviewer_id
    attempt.reviewed_at = datetime.now(UTC)
    attempt.review_note = note
    db.flush()
    write_audit(
        db,
        actor_user_id=reviewer_id,
        action="psych.attempt_reviewed",
        outcome="allowed",
        resource_type="psych_attempt",
        resource_id=attempt.id,
    )
    return attempt


def abandon_attempt(db: Session, attempt: PsychAttempt) -> PsychAttempt:
    if attempt.status in TERMINAL_STATUSES:
        raise PermissionError("INVALID_STATE")
    attempt.status = "abandoned"
    db.flush()
    return attempt


def log_result_access(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    subject_user_id: uuid.UUID | None,
    attempt: PsychAttempt,
    allowed: bool,
    ip: str | None = None,
) -> None:
    """Every read of a psych result lands in audit.access_events (B41+B37)."""
    db.add(
        AccessEvent(
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            action="psych.result.read",
            allowed=allowed,
            resource_type="psych_attempt",
            resource_id=attempt.id,
            ip=ip,
            detail={"status": attempt.status},
        )
    )
    db.flush()


def can_view_attempt(db: Session, attempt: PsychAttempt, user_id: uuid.UUID) -> bool:
    """نتیجه فرد دیگر دیده نشود — owner only; reviewers use the review endpoints."""
    return attempt.user_id == user_id


def _version_questions(db: Session, version_id: uuid.UUID) -> list[PsychQuestion]:
    return (
        db.execute(
            select(PsychQuestion)
            .where(PsychQuestion.version_id == version_id)
            .order_by(PsychQuestion.position)
        )
        .scalars()
        .all()
    )


def _test_kind(db: Session, test_id: uuid.UUID) -> str:
    test = db.get(PsychTest, test_id)
    return test.consent_kind if test else "psych_test"


def _uuid(value) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None
