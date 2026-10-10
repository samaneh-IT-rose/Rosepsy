from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "roz",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_default_queue="roz_default",
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="roz.process_outbox")
def process_outbox_task():
    """Drain the notification outbox (B12). Runs on the worker; also callable
    synchronously in tests via .apply()."""
    from app.core.db import SessionLocal
    from app.services.notifications import process_outbox

    with SessionLocal() as db:
        processed = process_outbox(db)
    return {"processed": processed}
