import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.notify import (
    Message,
    MessageThread,
    MessageThreadMember,
    Notification,
)
from app.services.notifications import get_or_create_preferences

router = APIRouter(tags=["notifications", "messages"])


class PreferencesIn(BaseModel):
    channel_sms: bool | None = None
    channel_email: bool | None = None
    channel_push: bool | None = None
    marketing_consent: bool | None = None


class ThreadIn(BaseModel):
    subject: str = Field(min_length=2, max_length=150)
    member_ids: list[uuid.UUID] = Field(max_length=10)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def _is_member(db: Session, thread_id: uuid.UUID, user_id) -> bool:
    return (
        db.execute(
            select(MessageThreadMember).where(
                MessageThreadMember.thread_id == thread_id,
                MessageThreadMember.user_id == user_id,
            )
        ).scalar_one_or_none()
        is not None
    )


@router.get("/notifications")
def list_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base = select(Notification).where(Notification.user_id == user.id)
    total = db.execute(
        select(func.count()).select_from(Notification).where(Notification.user_id == user.id)
    ).scalar_one()
    unread = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).scalar_one()
    rows = (
        db.execute(base.order_by(Notification.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(n.id),
                "event_type": n.event_type,
                "title": n.title,
                "body": n.body,
                "read": n.read_at is not None,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ],
        extra_meta={"total": total, "unread": unread, "limit": limit, "offset": offset},
    )


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        return error_response("NOTIFICATION_NOT_FOUND", "اعلان یافت نشد", 404)
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        db.commit()
    return envelope(data={"id": str(n.id), "read": True})


@router.get("/communication-preferences")
def get_preferences(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    pref = get_or_create_preferences(db, user.id)
    return envelope(
        data={
            "channel_sms": pref.channel_sms,
            "channel_email": pref.channel_email,
            "channel_push": pref.channel_push,
            "marketing_consent": pref.marketing_consent,
        }
    )


@router.put("/communication-preferences")
def put_preferences(
    body: PreferencesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = get_or_create_preferences(db, user.id)
    for field in ("channel_sms", "channel_email", "channel_push", "marketing_consent"):
        value = getattr(body, field)
        if value is not None:
            setattr(pref, field, value)
    db.commit()
    return envelope(
        data={
            "channel_sms": pref.channel_sms,
            "channel_email": pref.channel_email,
            "channel_push": pref.channel_push,
            "marketing_consent": pref.marketing_consent,
        }
    )


@router.post("/message-threads", status_code=201)
def create_thread(
    body: ThreadIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member_ids = list(dict.fromkeys(body.member_ids))  # dedupe, keep order
    if user.id in member_ids:
        return error_response(
            "INVALID_MEMBERS", "سازنده گفت‌وگو به‌طور خودکار عضو است", 422, field="member_ids"
        )
    thread = MessageThread(subject=body.subject.strip(), created_by=user.id)
    db.add(thread)
    db.flush()
    db.add(MessageThreadMember(thread_id=thread.id, user_id=user.id))
    for uid in member_ids:
        db.add(MessageThreadMember(thread_id=thread.id, user_id=uid))
    db.commit()
    return envelope(
        data={"id": str(thread.id), "subject": thread.subject, "members": len(member_ids) + 1}
    )


@router.get("/message-threads")
def list_threads(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = (
        db.execute(
            select(MessageThread)
            .join(MessageThreadMember, MessageThreadMember.thread_id == MessageThread.id)
            .where(MessageThreadMember.user_id == user.id)
            .order_by(MessageThread.created_at.desc())
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[{"id": str(t.id), "subject": t.subject} for t in rows]
    )


@router.get("/message-threads/{thread_id}/messages")
def thread_messages(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_member(db, thread_id, user.id):
        return error_response("THREAD_NOT_FOUND", "گفت‌وگو یافت نشد", 404)
    rows = (
        db.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at)
        )
        .scalars()
        .all()
    )
    return envelope(
        data=[
            {
                "id": str(m.id),
                "sender_id": str(m.sender_id),
                "body": m.body,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ]
    )


@router.post("/message-threads/{thread_id}/messages", status_code=201)
def post_message(
    thread_id: uuid.UUID,
    body: MessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_member(db, thread_id, user.id):
        return error_response("THREAD_NOT_FOUND", "گفت‌وگو یافت نشد", 404)
    msg = Message(thread_id=thread_id, sender_id=user.id, body=body.body.strip())
    db.add(msg)
    db.commit()
    return envelope(data={"id": str(msg.id), "thread_id": str(thread_id)})
