"""Celery tasks of the 定时任务 module.

``run_scheduled_task`` is the task registered in ``django_celery_beat``
(``aits:scheduled_task:<id>``); ``run_task_now`` backs the
``POST /api/scheduled-tasks/tasks/{id}/run/`` endpoint.

Both are idempotent and swallow execution errors inside ``dispatch_task`` — a
worker must never crash because a module is missing or an executor raised.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.scheduled_tasks.models import TaskExecutionLog
from apps.scheduled_tasks.services import dispatcher

logger = logging.getLogger(__name__)

RUN_SCHEDULED_TASK_NAME = "apps.scheduled_tasks.tasks.run_scheduled_task"
RUN_TASK_NOW_NAME = "apps.scheduled_tasks.tasks.run_task_now"


def _record_celery_task_id(log_id, celery_task_id) -> None:
    if not log_id or not celery_task_id:
        return
    try:
        TaskExecutionLog.objects.filter(pk=log_id).update(
            celery_task_id=str(celery_task_id)
        )
    except Exception:  # pragma: no cover - bookkeeping only
        logger.debug("failed to record celery id for log %s", log_id, exc_info=True)


@shared_task(bind=True, name=RUN_SCHEDULED_TASK_NAME)
def run_scheduled_task(self, task_id, execution_log_id=None):
    """Beat entrypoint: dispatch the task configured with ``task_id``."""
    log_id = dispatcher.dispatch_task(
        task_id,
        trigger_type="scheduled",
        execution_log_id=execution_log_id,
    )
    _record_celery_task_id(log_id, getattr(self.request, "id", None))
    return log_id


@shared_task(name=RUN_TASK_NOW_NAME)
def run_task_now(task_id, triggered_by_id=None, execution_log_id=None):
    """Manual run entrypoint (also used by the ``run`` API action)."""
    triggered_by = None
    if triggered_by_id:
        from django.contrib.auth import get_user_model

        triggered_by = get_user_model().objects.filter(pk=triggered_by_id).first()
    log_id = dispatcher.dispatch_task(
        task_id,
        triggered_by=triggered_by,
        trigger_type="manual",
        execution_log_id=execution_log_id,
    )
    _record_celery_task_id(
        log_id, getattr(getattr(run_task_now, "request", None), "id", None)
    )
    return log_id
