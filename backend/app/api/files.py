import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import envelope, error_response
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import request_id_var
from app.models.core import User
from app.models.files import File
from app.services import storage
from app.services.authz import write_audit
from app.services.av import scan_file

router = APIRouter(tags=["files"])


class IntentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=100)
    size_bytes: int = Field(gt=0)
    context: str = Field(default="general", pattern=r"^[a-z_]{2,32}$")


def _allowed(content_type: str) -> bool:
    allowed = [t.strip() for t in settings.FILE_ALLOWED_CONTENT_TYPES.split(",") if t.strip()]
    return content_type in allowed


def _data(f: File, extra: dict | None = None) -> dict:
    base = {
        "id": str(f.id),
        "filename": f.filename,
        "content_type": f.content_type,
        "size_bytes": int(f.size_bytes),
        "status": f.status,
        "context": f.context,
    }
    if extra:
        base.update(extra)
    return base


@router.post("/files/upload-intents", status_code=201)
def create_upload_intent(
    body: IntentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Issue a short-lived presigned PUT URL; bytes go straight to MinIO (B39)."""
    if not _allowed(body.content_type):
        return error_response(
            "CONTENT_TYPE_NOT_ALLOWED",
            "نوع فایل مجاز نیست؛ فقط تصویر و PDF پذیرفته می‌شود",
            422,
            field="content_type",
        )
    if body.size_bytes > settings.FILE_MAX_BYTES:
        return error_response(
            "FILE_TOO_LARGE",
            f"حداکثر حجم فایل {settings.FILE_MAX_BYTES // (1024 * 1024)} مگابایت است",
            422,
            field="size_bytes",
        )

    safe_name = body.filename.replace("\\", "/").split("/")[-1][:255]
    record = File(
        owner_user_id=user.id,
        context=body.context,
        filename=safe_name,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        storage_key=f"{body.context}/{uuid.uuid4().hex}",
        status="uploaded",
    )
    db.add(record)
    db.commit()
    url = storage.presigned_put(record.storage_key, settings.UPLOAD_URL_TTL_SECONDS)
    return envelope(
        data=_data(
            record,
            extra={
                "upload_url": url,
                "method": "PUT",
                "expires_in_seconds": settings.UPLOAD_URL_TTL_SECONDS,
            },
        )
    )


@router.post("/files/{file_id}/complete")
def complete_upload(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify the object landed, then scan: uploaded -> scanning -> clean|quarantined."""
    f = db.get(File, file_id)
    if f is None or f.owner_user_id != user.id:
        return error_response("FILE_NOT_FOUND", "فایل یافت نشد", 404)
    if f.status != "uploaded":
        return error_response(
            "INVALID_FILE_STATE", f"فایل در وضعیت {f.status} قابل تکمیل نیست", 409
        )

    stat = storage.stat_object(f.storage_key)
    if stat is None:
        return error_response(
            "OBJECT_NOT_UPLOADED", "هیچ محتوایی برای این فایل بارگذاری نشده است", 409
        )
    if stat["size"] != int(f.size_bytes):
        return error_response(
            "SIZE_MISMATCH", "حجم فایل بارگذاری‌شده با درخواست هم‌خوان نیست", 409
        )

    f.checksum = stat["etag"]
    f.status = "scanning"
    verdict = scan_file(
        filename=f.filename, content_type=f.content_type, size_bytes=stat["size"]
    )
    f.status = verdict
    db.commit()
    write_audit(
        db,
        actor_user_id=user.id,
        action="file.complete",
        outcome="allowed",
        resource_type="file",
        resource_id=f.id,
        request_id=request_id_var.get(),
        detail={"verdict": verdict},
    )
    return envelope(data=_data(f))


@router.get("/files/{file_id}/download-ticket")
def download_ticket(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Short-lived presigned GET; owner only; clean files only (B39 acceptance)."""
    f = db.get(File, file_id)
    if f is None or f.owner_user_id != user.id or f.status == "deleted":
        return error_response("FILE_NOT_FOUND", "فایل یافت نشد", 404)
    if f.status == "quarantined":
        return error_response("FILE_QUARANTINED", "فایل قرنطینه‌شده قابل دانلود نیست", 409)
    if f.status != "clean":
        return error_response("FILE_NOT_READY", "فایل هنوز آماده دانلود نیست", 409)

    url = storage.presigned_get(f.storage_key, settings.DOWNLOAD_TICKET_TTL_SECONDS)
    write_audit(
        db,
        actor_user_id=user.id,
        action="file.download_ticket",
        outcome="allowed",
        resource_type="file",
        resource_id=f.id,
        request_id=request_id_var.get(),
    )
    return envelope(
        data={
            "id": str(f.id),
            "download_url": url,
            "expires_in_seconds": settings.DOWNLOAD_TICKET_TTL_SECONDS,
        }
    )
