"""Courses API (B34+B35+B36): catalog, modules/lessons, enrollment, exams."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.edu import (
    Certificate,
    Course,
    CourseEnrollment,
    CourseExam,
    CourseModule,
    ExamAttempt,
    ExamQuestion,
    Lesson,
    LessonProgress,
    LessonVersion,
)
from app.services.authz import write_audit
from app.services.edu import (
    course_has_valid_lesson,
    get_or_create_enrollment,
    has_active_access,
    issue_certificate,
    score_attempt,
)

router = APIRouter(tags=["courses"])


# ─────────────── management (contents.manage = education manager) ───────────────


class CourseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    topic_id: uuid.UUID | None = None
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    instructor_name: str | None = Field(default=None, max_length=120)
    is_free: bool = True
    price: int = Field(default=0, ge=0)


class ModuleIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    position: int = Field(default=1, ge=1)


class LessonIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    lesson_type: str = Field(default="video", pattern=r"^(video|pdf)$")
    file_id: uuid.UUID | None = None
    duration_seconds: int = Field(default=0, ge=0)
    position: int = Field(default=1, ge=1)
    is_preview: bool = False


class ExamIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    pass_score: int = Field(default=60, ge=0, le=100)
    max_attempts: int = Field(default=1, ge=1, le=10)
    duration_minutes: int = Field(default=20, ge=1, le=240)


class QuestionIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0)
    weight: int = Field(default=1, ge=1)
    position: int = Field(default=1, ge=1)


def _course_data(c: Course) -> dict:
    return {
        "id": str(c.id),
        "title": c.title,
        "slug": c.slug,
        "summary": c.summary,
        "description": c.description,
        "instructor_name": c.instructor_name,
        "is_free": c.is_free,
        "price": int(c.price),
        "status": c.status,
        "published_at": c.published_at.isoformat() if c.published_at else None,
    }


@router.post("/courses", status_code=201)
def create_course(
    body: CourseIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    if not body.is_free and body.price <= 0:
        return error_response("COURSE_PRICE_INVALID", "دوره پولی باید قیمت مثبت داشته باشد", 422)
    if body.is_free and body.price != 0:
        return error_response("COURSE_PRICE_INVALID", "دوره رایگان باید قیمت صفر داشته باشد", 422)
    from app.api.contents import _slugify

    slug = (body.slug or _slugify(body.title))[:80]
    if db.execute(select(Course.id).where(Course.slug == slug)).scalar_one_or_none():
        return error_response("SLUG_EXISTS", "این نامک قبلاً استفاده شده است", 409)
    c = Course(
        title=body.title,
        slug=slug,
        topic_id=body.topic_id,
        summary=body.summary,
        description=body.description,
        instructor_user_id=user.id,
        instructor_name=body.instructor_name,
        is_free=body.is_free,
        price=body.price,
    )
    db.add(c)
    db.commit()
    return envelope(data=_course_data(c))


@router.get("/courses")
def list_my_managed_courses(
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Course).order_by(Course.created_at.desc()).limit(200)).scalars().all()
    return envelope(data=[_course_data(c) for c in rows])


@router.post("/courses/{course_id}/modules", status_code=201)
def add_module(
    course_id: uuid.UUID,
    body: ModuleIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    c = db.get(Course, course_id)
    if c is None:
        return error_response("COURSE_NOT_FOUND", "دوره یافت نشد", 404)
    m = CourseModule(course_id=course_id, title=body.title, position=body.position)
    db.add(m)
    db.commit()
    return envelope(data={"id": str(m.id), "title": m.title, "position": m.position})


@router.post("/modules/{module_id}/lessons", status_code=201)
def add_lesson(
    module_id: uuid.UUID,
    body: LessonIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    m = db.get(CourseModule, module_id)
    if m is None:
        return error_response("MODULE_NOT_FOUND", "فصل یافت نشد", 404)
    lesson = Lesson(
        module_id=module_id,
        title=body.title,
        lesson_type=body.lesson_type,
        file_id=body.file_id,
        duration_seconds=body.duration_seconds,
        position=body.position,
        is_preview=body.is_preview,
    )
    db.add(lesson)
    db.commit()
    return envelope(data={"id": str(lesson.id), "title": lesson.title, "version": lesson.version})


@router.put("/lessons/{lesson_id}")
def update_lesson(
    lesson_id: uuid.UUID,
    body: LessonIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        return error_response("LESSON_NOT_FOUND", "درس یافت نشد", 404)
    module = db.get(CourseModule, lesson.module_id)
    course = db.get(Course, module.course_id)
    if course.status == "published":
        # keep the published version before mutating (B34)
        db.add(
            LessonVersion(
                lesson_id=lesson.id,
                version=lesson.version,
                snapshot={
                    "title": lesson.title,
                    "lesson_type": lesson.lesson_type,
                    "duration_seconds": lesson.duration_seconds,
                    "position": lesson.position,
                    "is_preview": lesson.is_preview,
                },
            )
        )
        lesson.version += 1
    lesson.title = body.title
    lesson.lesson_type = body.lesson_type
    lesson.file_id = body.file_id
    lesson.duration_seconds = body.duration_seconds
    lesson.position = body.position
    lesson.is_preview = body.is_preview
    db.commit()
    return envelope(data={"id": str(lesson.id), "version": lesson.version})


@router.post("/courses/{course_id}/publish")
def publish_course(
    course_id: uuid.UUID,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    c = db.get(Course, course_id)
    if c is None:
        return error_response("COURSE_NOT_FOUND", "دوره یافت نشد", 404)
    if c.status == "published":
        return error_response("INVALID_TRANSITION", "دوره منتشر شده است", 409)
    if not course_has_valid_lesson(db, c.id):
        return error_response(
            "COURSE_NOT_PUBLISHABLE", "انتشار فقط با حداقل یک درس معتبر (دارای فایل) ممکن است", 422
        )
    c.status = "published"
    c.published_at = datetime.now(UTC)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="course.published",
        outcome="allowed",
        resource_type="course",
        resource_id=c.id,
    )
    return envelope(data=_course_data(c))


# ─────────────── public catalog ───────────────


@router.get("/public/courses")
def public_courses(
    topic_id: uuid.UUID | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Course).where(Course.status == "published").order_by(
        Course.published_at.desc()
    )
    if topic_id:
        stmt = stmt.where(Course.topic_id == topic_id)
    if q:
        stmt = stmt.where(Course.title.ilike(f"%{q.strip()}%"))
    rows = db.execute(stmt).scalars().all()
    return envelope(
        data=[
            {
                "title": c.title,
                "slug": c.slug,
                "summary": c.summary,
                "instructor_name": c.instructor_name,
                "is_free": c.is_free,
                "price": int(c.price),
            }
            for c in rows
        ]
    )


def _lesson_public(lesson: Lesson, *, enrolled: bool) -> dict:
    return {
        "id": str(lesson.id),
        "title": lesson.title,
        "lesson_type": lesson.lesson_type,
        "duration_seconds": lesson.duration_seconds,
        "is_preview": lesson.is_preview,
        "has_file": lesson.file_id is not None,
        "file_accessible": enrolled or lesson.is_preview,
        "version": lesson.version,
    }


@router.get("/public/courses/{slug}")
def public_course_detail(
    slug: str,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.execute(
        select(Course).where(Course.slug == slug, Course.status == "published")
    ).scalar_one_or_none()
    if c is None:
        return error_response("COURSE_NOT_FOUND", "دوره یافت نشد", 404)
    modules = db.execute(
        select(CourseModule)
        .where(CourseModule.course_id == c.id)
        .order_by(CourseModule.position)
    ).scalars().all()
    enrolled = user is not None and has_active_access(db, user.id, c.id)
    lessons_by_module: dict[uuid.UUID, list] = {}
    if modules:
        rows = db.execute(
            select(Lesson)
            .where(Lesson.module_id.in_([m.id for m in modules]))
            .order_by(Lesson.position)
        ).scalars().all()
        for lesson in rows:
            lessons_by_module.setdefault(lesson.module_id, []).append(lesson)
    exams = db.execute(
        select(CourseExam).where(
            CourseExam.course_id == c.id, CourseExam.is_active.is_(True)
        )
    ).scalars().all()
    return envelope(
        data={
            **_course_data(c),
            "enrolled": enrolled,
            "modules": [
                {
                    "id": str(m.id),
                    "title": m.title,
                    "position": m.position,
                    "lessons": [
                        _lesson_public(lesson, enrolled=enrolled)
                        for lesson in lessons_by_module.get(m.id, [])
                    ],
                }
                for m in modules
            ],
            "exams": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "pass_score": e.pass_score,
                    "max_attempts": e.max_attempts,
                    "duration_minutes": e.duration_minutes,
                }
                for e in exams
            ],
        }
    )


# ─────────────── enrollment (B35) ───────────────


class EnrollIn(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=80)


@router.post("/courses/{course_id}/enrollments", status_code=201)
def enroll(
    course_id: uuid.UUID,
    body: EnrollIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Course, course_id)
    if c is None or c.status != "published":
        return error_response("COURSE_NOT_FOUND", "دوره منتشرشده یافت نشد", 404)

    existing = db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == user.id, CourseEnrollment.course_id == c.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        # duplicate request never duplicates access (B35)
        return envelope(
            data={
                "enrollment_id": str(existing.id),
                "status": existing.status,
                "course_id": str(c.id),
                "already_enrolled": True,
            },
            extra_meta={"idempotent_replay": True},
        )

    if c.is_free:
        enrollment = get_or_create_enrollment(
            db, user_id=user.id, course=c, source="free"
        )
        db.commit()
        return envelope(
            data={
                "enrollment_id": str(enrollment.id),
                "status": enrollment.status,
                "course_id": str(c.id),
                "already_enrolled": False,
            }
        )

    # paid: pending enrollment + an order the user pays via the gateway
    enrollment = get_or_create_enrollment(
        db, user_id=user.id, course=c, source="purchase"
    )
    from app.models.finance import Order

    order = Order(
        user_id=user.id,
        order_type="course",
        amount=int(c.price),
        currency="IRR",
        status="awaiting_payment",
        idempotency_key=(body.idempotency_key if body else None) or f"course-{enrollment.id}",
        price_snapshot={"kind": "course", "course_id": str(c.id), "title": c.title},
    )
    db.add(order)
    db.flush()
    enrollment.order_id = order.id
    db.commit()
    return envelope(
        data={
            "enrollment_id": str(enrollment.id),
            "status": enrollment.status,
            "course_id": str(c.id),
            "order_id": str(order.id),
            "already_enrolled": False,
        }
    )


@router.get("/my-courses")
def my_courses(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(CourseEnrollment).where(CourseEnrollment.user_id == user.id)
    ).scalars().all()
    data = []
    for e in rows:
        c = db.get(Course, e.course_id)
        total_lessons = (
            db.execute(
                select(func.count())
                .select_from(Lesson)
                .join(CourseModule, CourseModule.id == Lesson.module_id)
                .where(CourseModule.course_id == c.id)
            ).scalar_one()
            if c
            else 0
        )
        done = (
            db.execute(
                select(func.count())
                .select_from(LessonProgress)
                .join(Lesson, Lesson.id == LessonProgress.lesson_id)
                .join(CourseModule, CourseModule.id == Lesson.module_id)
                .where(
                    CourseModule.course_id == c.id, LessonProgress.user_id == user.id
                )
            ).scalar_one()
            if c
            else 0
        )
        certs = db.execute(
            select(Certificate.certificate_number).where(
                Certificate.user_id == user.id, Certificate.course_id == e.course_id
            )
        ).scalars().all()
        data.append(
            {
                "enrollment_id": str(e.id),
                "course_id": str(e.course_id),
                "title": c.title if c else None,
                "slug": c.slug if c else None,
                "status": e.status,
                "progress": {"completed_lessons": done, "total_lessons": total_lessons},
                "certificates": list(certs),
            }
        )
    return envelope(data=data)


@router.post("/lessons/{lesson_id}/progress", status_code=201)
def mark_progress(
    lesson_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        return error_response("LESSON_NOT_FOUND", "درس یافت نشد", 404)
    module = db.get(CourseModule, lesson.module_id)
    if not has_active_access(db, user.id, module.course_id):
        return error_response("NO_ACCESS", "دسترسی فعال به این دوره ندارید", 403)
    exists = db.execute(
        select(LessonProgress.id).where(
            LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson_id
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(LessonProgress(user_id=user.id, lesson_id=lesson_id))
        db.commit()
    return envelope(data={"lesson_id": str(lesson_id), "completed": True})


# ─────────────── exams & certificates (B36) ───────────────


@router.post("/courses/{course_id}/exams", status_code=201)
def create_exam(
    course_id: uuid.UUID,
    body: ExamIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    c = db.get(Course, course_id)
    if c is None:
        return error_response("COURSE_NOT_FOUND", "دوره یافت نشد", 404)
    exam = CourseExam(
        course_id=course_id,
        title=body.title,
        pass_score=body.pass_score,
        max_attempts=body.max_attempts,
        duration_minutes=body.duration_minutes,
    )
    db.add(exam)
    db.commit()
    return envelope(data={"id": str(exam.id), "title": exam.title})


@router.post("/course-exams/{exam_id}/questions", status_code=201)
def add_question(
    exam_id: uuid.UUID,
    body: QuestionIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    exam = db.get(CourseExam, exam_id)
    if exam is None:
        return error_response("EXAM_NOT_FOUND", "آزمون یافت نشد", 404)
    if body.correct_index >= len(body.options):
        return error_response("QUESTION_INVALID", "گزینه صحیح خارج از محدوده است", 422)
    q = ExamQuestion(
        exam_id=exam_id,
        text=body.text,
        options=body.options,
        correct_index=body.correct_index,
        weight=body.weight,
        position=body.position,
    )
    db.add(q)
    db.commit()
    return envelope(data={"id": str(q.id)})


@router.post("/course-exams/{exam_id}/attempts", status_code=201)
def start_attempt(
    exam_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = db.get(CourseExam, exam_id)
    if exam is None or not exam.is_active:
        return error_response("EXAM_NOT_FOUND", "آزمون فعال یافت نشد", 404)
    if not has_active_access(db, user.id, exam.course_id):
        return error_response("NO_ACCESS", "فقط ثبت‌نام‌شده‌ها مجاز به آزمون هستند", 403)
    taken = db.execute(
        select(func.count())
        .select_from(ExamAttempt)
        .where(ExamAttempt.exam_id == exam_id, ExamAttempt.user_id == user.id)
    ).scalar_one()
    if taken >= exam.max_attempts:
        return error_response("ATTEMPT_CAP_REACHED", "سقف تلاش این آزمون تکمیل شده است", 409)
    active = db.execute(
        select(ExamAttempt).where(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user.id,
            ExamAttempt.status == "in_progress",
        )
    ).scalar_one_or_none()
    if active is not None:
        return envelope(data={"attempt_id": str(active.id), "resumed": True})
    attempt = ExamAttempt(exam_id=exam_id, user_id=user.id)
    db.add(attempt)
    db.commit()
    return envelope(data={"attempt_id": str(attempt.id), "resumed": False})


class SubmitIn(BaseModel):
    answers: list[dict]


@router.post("/course-attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: uuid.UUID,
    body: SubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    attempt = db.get(ExamAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        return error_response("ATTEMPT_NOT_FOUND", "تلاش آزمون یافت نشد", 404)
    if attempt.status != "in_progress":
        return error_response("ATTEMPT_ALREADY_SUBMITTED", "این تلاش قبلاً ارسال شده است", 409)
    attempt = score_attempt(db, attempt, body.answers)
    certificate_number = None
    if attempt.status == "passed":
        cert = issue_certificate(db, attempt, actor_user_id=user.id)
        certificate_number = cert.certificate_number
    db.commit()
    return envelope(
        data={
            "attempt_id": str(attempt.id),
            "score": attempt.score,
            "status": attempt.status,
            "certificate_number": certificate_number,
        }
    )


@router.get("/my-certificates")
def my_certificates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Certificate).where(Certificate.user_id == user.id)
    ).scalars().all()
    data = []
    for cert in rows:
        c = db.get(Course, cert.course_id)
        data.append(
            {
                "id": str(cert.id),
                "certificate_number": cert.certificate_number,
                "course_title": c.title if c else None,
                "issued_at": cert.issued_at.isoformat(),
                "verification_code": cert.verification_code,
            }
        )
    return envelope(data=data)


@router.get("/certificates/verify/{code}")
def verify_certificate(code: str, db: Session = Depends(get_db)):
    """Public limited verification (B36): masked holder, no personal data."""
    cert = db.execute(
        select(Certificate).where(Certificate.verification_code == code.strip())
    ).scalar_one_or_none()
    if cert is None:
        return error_response("CERTIFICATE_NOT_FOUND", "گواهی یافت نشد", 404)
    c = db.get(Course, cert.course_id)
    holder = db.get(User, cert.user_id)
    phone = (holder.phone_e164 or "") if holder else ""
    masked = (phone[:4] + "****" + phone[-3:]) if len(phone) >= 8 else "****"
    return envelope(
        data={
            "valid": True,
            "certificate_number": cert.certificate_number,
            "course_title": c.title if c else None,
            "holder_masked": masked,
            "issued_at": cert.issued_at.isoformat(),
        }
    )
