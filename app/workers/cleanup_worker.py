from celery import shared_task


@shared_task
def cleanup_expired_data() -> int:
    """Retention policies can delete expired raw payloads without deleting analytics."""
    return 0
