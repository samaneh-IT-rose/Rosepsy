"""CMS API (B33): manage contents with review flow + public read endpoints."""

import re
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.content import Content, ContentRevision, ContentTopic
from app.models.core import User
from app.models.topics import Topic
from app.services.authz import write_audit

router = APIRouter(tags=["contents"])

CONTENT_TRANSITIONS = {
    ("draft", "in_review"),
    ("in_review", "published"),
    ("in_review", "rejected"),
    ("published", "archived"),
    ("rejected", "draft"),
    ("archived", "draft"),
}


def _slugify(title: str) -> str:
    slug = re.sub(r"\s+", "-", title.strip().lower())[:70]
    return re.sub(r"[^a-z0-9\u0600-\u06FF-]", "", slug) or uuid.uuid4().hex[:12]


def content_data(c: Content, topics: list[str] | None = None) -> dict:
    return {
        "id": str(c.id),
        "type": c.type,
        "title": c.title,
        "slug": c.slug,
        "summary": c.summary,
        "body": c.body,
        "status": c.status,
        "source": c.source,
        "seo_title": c.seo_title,
        "seo_description": c.seo_description,
        "published_at": c.published_at.isoformat() if c.published_at else None,
        "topics": topics or [],
        "created_at": c.created_at.isoformat(),
    }


def _content_topics(db: Session, content_id: uuid.UUID) -> list[str]:
    rows = db.execute(
        select(Topic.name).join(ContentTopic, ContentTopic.topic_id == Topic.id).where(
            ContentTopic.content_id == content_id
        )
    ).scalars().all()
    return list(rows)


class ContentIn(BaseModel):
    type: str = Field(pattern=r"^(article|news|podcast|video)$")
    title: str = Field(min_length=3, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=20000)
    media_file_id: uuid.UUID | None = None
    source: str | None = Field(default=None, max_length=200)
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=300)
    topic_ids: list[uuid.UUID] = []


def _save_topics(db: Session, content_id: uuid.UUID, topic_ids: list[uuid.UUID]) -> None:
    db.execute(
        ContentTopic.__table__.delete().where(ContentTopic.content_id == content_id)
    )
    for tid in dict.fromkeys(topic_ids):
        db.add(ContentTopic(content_id=content_id, topic_id=tid))


def _snapshot(c: Content, topics: list[str]) -> dict:
    return {
        "type": c.type,
        "title": c.title,
        "slug": c.slug,
        "summary": c.summary,
        "body": c.body,
        "status": c.status,
        "topics": topics,
    }


@router.post("/contents", status_code=201)
def create_content(
    body: ContentIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    slug = (body.slug or _slugify(body.title))[:80]
    if db.execute(select(Content.id).where(Content.slug == slug)).scalar_one_or_none():
        return error_response("SLUG_EXISTS", "این نامک قبلاً استفاده شده است", 409)
    c = Content(
        type=body.type,
        title=body.title,
        slug=slug,
        summary=body.summary,
        body=body.body,
        media_file_id=body.media_file_id,
        source=body.source,
        seo_title=body.seo_title,
        seo_description=body.seo_description,
        status="draft",
        author_user_id=user.id,
    )
    db.add(c)
    db.flush()
    _save_topics(db, c.id, body.topic_ids)
    db.add(
        ContentRevision(
            content_id=c.id,
            version=1,
            snapshot=_snapshot(c, _content_topics(db, c.id)),
            editor_user_id=user.id,
        )
    )
    db.commit()
    return envelope(data=content_data(c, _content_topics(db, c.id)))


@router.get("/contents")
def list_contents(
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Content).order_by(Content.created_at.desc()).limit(200)
    ).scalars().all()
    return envelope(data=[content_data(c, _content_topics(db, c.id)) for c in rows])


@router.get("/contents/{content_id}")
def get_content(
    content_id: uuid.UUID,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    c = db.get(Content, content_id)
    if c is None:
        return error_response("CONTENT_NOT_FOUND", "محتوا یافت نشد", 404)
    revisions = db.execute(
        select(ContentRevision)
        .where(ContentRevision.content_id == c.id)
        .order_by(ContentRevision.version.desc())
    ).scalars().all()
    data = content_data(c, _content_topics(db, c.id))
    data["revisions"] = [
        {"version": r.version, "snapshot": r.snapshot, "created_at": r.created_at.isoformat()}
        for r in revisions
    ]
    return envelope(data=data)


@router.put("/contents/{content_id}")
def update_content(
    content_id: uuid.UUID,
    body: ContentIn,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    c = db.get(Content, content_id)
    if c is None:
        return error_response("CONTENT_NOT_FOUND", "محتوا یافت نشد", 404)
    last_version = (
        db.execute(
            select(ContentRevision.version)
            .where(ContentRevision.content_id == c.id)
            .order_by(ContentRevision.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        or 0
    )

    c.type = body.type
    c.title = body.title
    c.summary = body.summary
    c.body = body.body
    c.media_file_id = body.media_file_id
    c.source = body.source
    c.seo_title = body.seo_title
    c.seo_description = body.seo_description
    if body.slug and body.slug != c.slug:
        clash = db.execute(
            select(Content.id).where(Content.slug == body.slug, Content.id != c.id)
        ).scalar_one_or_none()
        if clash:
            return error_response("SLUG_EXISTS", "این نامک قبلاً استفاده شده است", 409)
        c.slug = body.slug
    _save_topics(db, c.id, body.topic_ids)
    db.flush()
    db.add(
        ContentRevision(
            content_id=c.id,
            version=last_version + 1,
            snapshot=_snapshot(c, _content_topics(db, c.id)),
            editor_user_id=user.id,
        )
    )
    db.commit()
    return envelope(data=content_data(c, _content_topics(db, c.id)))


class TransitionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


@router.post("/contents/{content_id}/{transition}")
def transition_content(
    content_id: uuid.UUID,
    transition: str,
    body: TransitionIn | None = None,
    user: User = Depends(require_permission("contents.manage")),
    db: Session = Depends(get_db),
):
    if transition not in ("submit-review", "publish", "reject", "archive", "back-to-draft"):
        return error_response("INVALID_TRANSITION", "انتقال نامعتبر است", 404)
    c = db.get(Content, content_id)
    if c is None:
        return error_response("CONTENT_NOT_FOUND", "محتوا یافت نشد", 404)
    target = {
        "submit-review": "in_review",
        "publish": "published",
        "reject": "rejected",
        "archive": "archived",
        "back-to-draft": "draft",
    }[transition]
    if (c.status, target) not in CONTENT_TRANSITIONS:
        return error_response(
            "INVALID_TRANSITION", f"انتقال از {c.status} به {target} مجاز نیست", 409
        )
    if target == "published":
        has_media = c.media_file_id is not None or (c.body or "").strip()
        if not has_media:
            return error_response(
                "CONTENT_NOT_PUBLISHABLE", "محتوای معتبر برای انتشار وجود ندارد", 422
            )
    c.status = target
    if target == "published":
        from datetime import UTC, datetime

        c.published_at = datetime.now(UTC)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action=f"content.{target}",
        outcome="allowed",
        resource_type="content",
        resource_id=c.id,
        detail={"reason": body.reason if body else None},
    )
    return envelope(data=content_data(c, _content_topics(db, c.id)))


# ─────────────── public endpoints (published only) ───────────────


@router.get("/public/contents")
def public_contents(
    type: str | None = None,
    topic_id: uuid.UUID | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Content)
        .where(Content.status == "published")
        .order_by(Content.published_at.desc())
        .limit(50)
    )
    if type:
        stmt = stmt.where(Content.type == type)
    if topic_id:
        stmt = stmt.join(ContentTopic, ContentTopic.content_id == Content.id).where(
            ContentTopic.topic_id == topic_id
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Content.title.ilike(like), Content.summary.ilike(like))
        )
    rows = db.execute(stmt).scalars().all()
    return envelope(
        data=[
            {
                "type": c.type,
                "title": c.title,
                "slug": c.slug,
                "summary": c.summary,
                "published_at": c.published_at.isoformat() if c.published_at else None,
                "topics": _content_topics(db, c.id),
            }
            for c in rows
        ]
    )


@router.get("/public/contents/{slug}")
def public_content_detail(slug: str, db: Session = Depends(get_db)):
    c = db.execute(
        select(Content).where(Content.slug == slug, Content.status == "published")
    ).scalar_one_or_none()
    if c is None:
        return error_response("CONTENT_NOT_FOUND", "محتوا یافت نشد", 404)
    return envelope(data=content_data(c, _content_topics(db, c.id)))
