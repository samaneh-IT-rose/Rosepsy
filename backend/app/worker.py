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
