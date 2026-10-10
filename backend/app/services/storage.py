"""Object storage layer (B39/ADR-04): MinIO / S3-compatible.

The DB never stores file bytes - only metadata + storage_key (spec s.03).
"""

from datetime import timedelta
from functools import lru_cache

from minio import Minio

from app.core.config import settings


@lru_cache
def get_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket() -> None:
    client = get_client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


def presigned_put(storage_key: str, ttl_seconds: int) -> str:
    ensure_bucket()
    return get_client().presigned_put_object(
        settings.MINIO_BUCKET, storage_key, expires=timedelta(seconds=ttl_seconds)
    )


def presigned_get(storage_key: str, ttl_seconds: int) -> str:
    ensure_bucket()
    return get_client().presigned_get_object(
        settings.MINIO_BUCKET, storage_key, expires=timedelta(seconds=ttl_seconds)
    )


def stat_object(storage_key: str) -> dict | None:
    """Returns {size, etag} or None if the object does not exist."""
    try:
        st = get_client().stat_object(settings.MINIO_BUCKET, storage_key)
        return {"size": int(st.size), "etag": str(st.etag)}
    except Exception:
        return None
