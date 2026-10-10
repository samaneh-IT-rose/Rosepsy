import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class ClinicalRecord(Base):
    """One digital record per user (B13). Created only with active treatment consent."""

    __tablename__ = "clinical_records"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str | None] = mapped_column(String(1000))
    risk_level: Mapped[str] = mapped_column(String(12), default="unknown")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RecordFile(Base):
    """Link between a secure file (B39) and a clinical record (B13)."""

    __tablename__ = "record_files"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.clinical_records.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.files.id", ondelete="CASCADE")
    )
    attached_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    title_fa: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuestionnaireVersion(Base):
    """Immutable form definition (B14). Active = highest number per questionnaire."""

    __tablename__ = "questionnaire_versions"
    __table_args__ = (
        UniqueConstraint("questionnaire_id", "version", name="ux_clin_qv_q_ver"),
        {"schema": "clinical"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.questionnaires.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    schema_json: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Submission(Base):
    """Answers locked to a questionnaire version (B14)."""

    __tablename__ = "submissions"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.clinical_records.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.questionnaire_versions.id", ondelete="RESTRICT")
    )
    answers: Mapped[dict] = mapped_column(JSONB)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Encounter(Base):
    """Therapy session (B15/B16). State machine per spec s.09a:
    scheduled -> in_progress -> completed | cancelled | no_show."""

    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_clinical_encounters_range"),
        {"schema": "clinical"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.clinical_records.id", ondelete="CASCADE"), index=True
    )
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.consultants.id", ondelete="CASCADE"), index=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("booking.appointments.id", ondelete="SET NULL"), unique=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EncounterNote(Base):
    """Professional note (B15). After confirm, the text is frozen forever;
    corrections go to EncounterAmendment rows only."""

    __tablename__ = "encounter_notes"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.encounters.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(String(5000))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EncounterAmendment(Base):
    """Append-only correction referencing a confirmed note (B15)."""

    __tablename__ = "encounter_amendments"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clinical.encounter_notes.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.users.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(String(5000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
