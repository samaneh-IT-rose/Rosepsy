"""Feedback API (B23): surveys + support tickets (no clinical data exposure)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.permissions import require_permission
from app.api.schemas import envelope, error_response
from app.core.db import get_db
from app.models.core import User
from app.models.feedback import SupportTicket, SurveyResponse, TicketMessage
from app.services.authz import has_permission, write_audit

router = APIRouter(tags=["feedback"])

TICKET_OPEN_STATUSES = ("open", "in_progress")


class SurveyIn(BaseModel):
    appointment_id: uuid.UUID | None = None
    score: int = Field(ge=0, le=10)
    comment: str | None = Field(default=None, max_length=1000)


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=5, max_length=4000)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high)$")


class TicketMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TicketStatusIn(BaseModel):
    status: str = Field(pattern=r"^(in_progress|resolved|closed)$")


def _ticket_data(t: SupportTicket, with_messages: bool = False, db: Session | None = None) -> dict:
    data = {
        "id": str(t.id),
        "user_id": str(t.user_id),
        "subject": t.subject,
        "status": t.status,
        "priority": t.priority,
        "created_at": t.created_at.isoformat(),
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
    }
    if with_messages and db is not None:
        msgs = db.execute(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == t.id)
            .order_by(TicketMessage.created_at)
        ).scalars().all()
        data["messages"] = [
            {
                "id": str(m.id),
                "author_id": str(m.author_id),
                "body": m.body,
                "is_staff": m.is_staff,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ]
    return data


@router.post("/survey-responses", status_code=201)
def submit_survey(
    body: SurveyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.appointment_id is not None:
        exists = db.execute(
            select(SurveyResponse.id).where(
                SurveyResponse.appointment_id == body.appointment_id
            )
        ).scalar_one_or_none()
        if exists is not None:
            return error_response("SURVEY_EXISTS", "برای این جلسه نظرسنجی ثبت شده است", 409)
    row = SurveyResponse(
        user_id=user.id,
        appointment_id=body.appointment_id,
        score=body.score,
        comment=body.comment,
    )
    db.add(row)
    db.commit()
    return envelope(data={"id": str(row.id), "score": row.score})


@router.post("/support-tickets", status_code=201)
def create_ticket(
    body: TicketIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = SupportTicket(user_id=user.id, subject=body.subject, body=body.body,
                           priority=body.priority)
    db.add(ticket)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="ticket.create",
        outcome="allowed",
        resource_type="support_ticket",
        resource_id=ticket.id,
    )
    return envelope(data=_ticket_data(ticket))


@router.get("/support-tickets")
def list_tickets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    staff = has_permission(db, user.id, "tickets.manage")
    stmt = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(200)
    if not staff:
        stmt = stmt.where(SupportTicket.user_id == user.id)
    rows = db.execute(stmt).scalars().all()
    return envelope(data=[_ticket_data(t) for t in rows])


@router.get("/support-tickets/{ticket_id}")
def get_ticket(
    ticket_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        return error_response("TICKET_NOT_FOUND", "تیکت یافت نشد", 404)
    if t.user_id != user.id and not has_permission(db, user.id, "tickets.manage"):
        return error_response("TICKET_NOT_FOUND", "تیکت یافت نشد", 404)
    return envelope(data=_ticket_data(t, with_messages=True, db=db))


@router.post("/support-tickets/{ticket_id}/messages", status_code=201)
def post_ticket_message(
    ticket_id: uuid.UUID,
    body: TicketMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        return error_response("TICKET_NOT_FOUND", "تیکت یافت نشد", 404)
    staff = has_permission(db, user.id, "tickets.manage")
    if t.user_id != user.id and not staff:
        return error_response("TICKET_NOT_FOUND", "تیکت یافت نشد", 404)
    if t.status not in TICKET_OPEN_STATUSES:
        return error_response("TICKET_CLOSED", "تیکت بسته شده است", 409)
    msg = TicketMessage(
        ticket_id=t.id, author_id=user.id, body=body.body, is_staff=staff
    )
    db.add(msg)
    if staff and t.status == "open":
        t.status = "in_progress"
    db.commit()
    return envelope(
        data={"id": str(msg.id), "is_staff": msg.is_staff, "ticket_status": t.status}
    )


@router.post("/support-tickets/{ticket_id}/status")
def change_ticket_status(
    ticket_id: uuid.UUID,
    body: TicketStatusIn,
    user: User = Depends(require_permission("tickets.manage")),
    db: Session = Depends(get_db),
):
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        return error_response("TICKET_NOT_FOUND", "تیکت یافت نشد", 404)
    if t.status in ("resolved", "closed"):
        return error_response("INVALID_TICKET_TRANSITION", "انتقال وضعیت مجاز نیست", 409)
    t.status = body.status
    if body.status == "resolved":
        t.resolved_at = datetime.now(UTC)
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="ticket.status",
        outcome="allowed",
        resource_type="support_ticket",
        resource_id=t.id,
        detail={"to": body.status},
    )
    return envelope(data=_ticket_data(t))
