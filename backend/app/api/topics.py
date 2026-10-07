import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.core import User
from app.models.topics import Topic
from app.services.authz import write_audit

router = APIRouter(tags=["topics"])


class TopicIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class TopicPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    is_active: bool | None = None


def _data(t: Topic) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "parent_id": str(t.parent_id) if t.parent_id else None,
        "description": t.description,
        "sort_order": t.sort_order,
        "is_active": t.is_active,
    }


def _would_cycle(db: Session, topic_id: uuid.UUID, new_parent_id: uuid.UUID) -> bool:
    """Walk the ancestor chain of the candidate parent; hitting the topic = cycle."""
    seen: set[uuid.UUID] = set()
    current: uuid.UUID | None = new_parent_id
    while current is not None:
        if current == topic_id or current in seen:
            return True
        seen.add(current)
        current = db.execute(
            select(Topic.parent_id).where(Topic.id == current)
        ).scalar_one_or_none()
    return False


@router.post("/topics", status_code=201)
def create_topic(
    body: TopicIn,
    user: User = Depends(require_permission("topics.manage")),
    db: Session = Depends(get_db),
):
    if db.execute(select(Topic).where(Topic.slug == body.slug)).scalar_one_or_none():
        return error_response("DUPLICATE_SLUG", "این slug قبلاً ثبت شده است", 409)
    if body.parent_id is not None:
        parent = db.get(Topic, body.parent_id)
        if parent is None:
            return error_response("PARENT_NOT_FOUND", "موضوع والد یافت نشد", 404)
        if _would_cycle(db, parent.id, parent.parent_id or body.parent_id) or (
            parent.parent_id is not None and False
        ):
            pass  # parent always attaches below; cycles only arise on reparent
    t = Topic(
        name=body.name.strip(),
        slug=body.slug,
        parent_id=body.parent_id,
        description=body.description,
        sort_order=body.sort_order,
    )
    db.add(t)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="topic.create",
        outcome="allowed",
        resource_type="topic",
        resource_id=t.id,
        request_id=request_id_var.get(),
    )
    return envelope(data=_data(t))


@router.get("/topics")
def list_topics(
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.authz import has_permission

    stmt = select(Topic)
    if include_inactive:
        if not has_permission(db, user.id, "topics.manage"):
            return error_response("FORBIDDEN", "دسترسی غیرمجاز است", 403)
    else:
        stmt = stmt.where(Topic.is_active.is_(True))
    rows = db.execute(stmt.order_by(Topic.sort_order, Topic.name)).scalars().all()
    return envelope(data=[_data(t) for t in rows])


@router.patch("/topics/{topic_id}")
def patch_topic(
    topic_id: uuid.UUID,
    body: TopicPatchIn,
    user: User = Depends(require_permission("topics.manage")),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if topic is None:
        return error_response("TOPIC_NOT_FOUND", "موضوع یافت نشد", 404)

    if "parent_id" in body.model_fields_set and body.parent_id != topic.parent_id:
        if body.parent_id is not None:
            if body.parent_id == topic.id:
                return error_response(
                    "TOPIC_CYCLE", "موضوع نمی‌تواند والد خودش باشد", 409
                )
            if db.get(Topic, body.parent_id) is None:
                return error_response("PARENT_NOT_FOUND", "موضوع والد یافت نشد", 404)
            if _would_cycle(db, topic.id, body.parent_id):
                return error_response(
                    "TOPIC_CYCLE", "انتقال والد چرخه در درخت ایجاد می‌کند", 409
                )
        topic.parent_id = body.parent_id

    if body.name is not None:
        topic.name = body.name.strip()
    if "description" in body.model_fields_set:
        topic.description = body.description
    if "sort_order" in body.model_fields_set:
        topic.sort_order = body.sort_order
    if body.is_active is not None:
        topic.is_active = body.is_active
    db.commit()
    return envelope(data=_data(topic))


@router.delete("/topics/{topic_id}")
def delete_topic(
    topic_id: uuid.UUID,
    user: User = Depends(require_permission("topics.manage")),
    db: Session = Depends(get_db),
):
    """Hard delete only for leaves; topics with children must be archived instead."""
    topic = db.get(Topic, topic_id)
    if topic is None:
        return error_response("TOPIC_NOT_FOUND", "موضوع یافت نشد", 404)
    children = db.execute(
        select(func.count()).select_from(Topic).where(Topic.parent_id == topic_id)
    ).scalar_one()
    if children:
        return error_response(
            "TOPIC_HAS_CHILDREN",
            "موضوع دارای زیر‌موضوع است؛ ابتدا زیر‌موضوع‌ها را منتقل یا حذف کنید",
            409,
        )
    db.delete(topic)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="topic.delete",
        outcome="allowed",
        resource_type="topic",
        resource_id=topic_id,
        request_id=request_id_var.get(),
    )
    return envelope(data={"deleted": True})


@router.get("/public/topics")
def public_topics(db: Session = Depends(get_db)):
    rows = (
        db.execute(
            select(Topic)
            .where(Topic.is_active.is_(True))
            .order_by(Topic.sort_order, Topic.name)
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {"id": str(t.id), "name": t.name, "slug": t.slug, "parent_id": str(t.parent_id) if t.parent_id else None}
            for t in rows
        ]
    )
