from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("goofish_finder", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.search_worker.*": {"queue": "searches"},
        "app.workers.notification_worker.*": {"queue": "notifications"},
    },
    imports=(
        "app.workers.search_worker",
        "app.workers.notification_worker",
        "app.workers.cleanup_worker",
    ),
    beat_schedule={
        "enqueue-due-searches": {
            "task": "app.workers.search_worker.enqueue_due_searches",
            "schedule": 60.0,
        },
        "dispatch-alerts": {
            "task": "app.workers.notification_worker.dispatch_pending_alerts",
            "schedule": 20.0,
        },
    },
)
celery_app.autodiscover_tasks(["app.workers"])
