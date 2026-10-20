"""Keep ``django_celery_beat`` in sync with :class:`ScheduledTask` rows.

Both hooks run inside ``transaction.on_commit`` so beat never reads a row that
the surrounding transaction has not committed yet (and so a rolled back save
does not leave an orphan ``PeriodicTask`` behind).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.scheduled_tasks.models import ScheduledTask, periodic_task_name_for

logger = logging.getLogger(__name__)


def sync_periodic_task_now(task_id) -> None:
    """Sync the beat row for ``task_id`` (no-op when the task disappeared)."""
    task = ScheduledTask.objects.filter(pk=task_id).first()
    if task is None:
        ScheduledTask.delete_periodic_task_by_name(periodic_task_name_for(task_id))
        return
    try:
        task.sync_periodic_task()
    except Exception:  # pragma: no cover - beat must not break the caller
        logger.warning("failed to sync periodic task for %s", task_id, exc_info=True)


@receiver(post_save, sender=ScheduledTask, dispatch_uid="scheduled_tasks.post_save_sync")
def synchronize_periodic_task(sender, instance, **kwargs) -> None:
    """Create/update the ``PeriodicTask`` after every save (deferred)."""
    task_id = instance.pk
    if task_id is None:
        return
    transaction.on_commit(lambda: sync_periodic_task_now(task_id))


@receiver(post_delete, sender=ScheduledTask, dispatch_uid="scheduled_tasks.post_delete_cleanup")
def remove_periodic_task(sender, instance, **kwargs) -> None:
    """Delete the mirrored ``PeriodicTask`` when the task is deleted (deferred)."""
    name = periodic_task_name_for(instance.pk)
    if not name:
        return
    transaction.on_commit(lambda: ScheduledTask.delete_periodic_task_by_name(name))
