"""Celery tasks for the 通知中心 module.

The synchronous ``trigger_notification`` service is the single entry point used by
scheduled_tasks / performance.  This task is only a convenience wrapper for callers
that must not block their own request/worker (it is eager in ``AITS_ENV=test``).
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="notifications.trigger_notification_task")
def trigger_notification_task(self, scheduled_task=None, execution_log=None, result=None):
    """Best-effort async wrapper; never raises into the calling worker."""
    from apps.notifications.services import trigger_notification

    try:
        return trigger_notification(scheduled_task, execution_log, result)
    except Exception as exc:  # noqa: BLE001 - notification is never fatal
        logger.exception("notifications: async trigger failed: %s", exc)
        return {"sent": 0, "failed": 0, "results": [], "error": str(exc)}
