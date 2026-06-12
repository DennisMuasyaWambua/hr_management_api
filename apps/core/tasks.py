"""Celery tasks for the core app: notification delivery with retry."""
from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def deliver_notification(self, log_id: str):
    """Deliver a queued NotificationLog through its channel, retrying on failure."""
    from apps.core.models import NotificationLog
    from apps.core.services import notifications as notif

    try:
        log = NotificationLog.objects.get(id=log_id)
    except NotificationLog.DoesNotExist:
        return f'log {log_id} missing'
    if log.status in ('sent', 'delivered'):
        return 'already sent'

    sender = notif.SENDERS.get(log.channel)
    if sender is None:
        return f'unknown channel {log.channel}'
    if log.channel == 'email':
        result = sender(log.recipient, log.subject, log.body, log=log)
    else:
        result = sender(log.recipient, log.body, log=log)
    if result.status == 'failed' and self.request.retries < self.max_retries:
        raise self.retry()
    return result.status
