"""Celery tasks for the 性能测试 module."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.performance.services.execution import run_execution

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="performance.execute_scenario")
def execute_scenario_task(self, execution_id):
    """Run a ``pending`` performance execution (``PerformanceExecution.id``).

    ``run_execution`` already records errors on the row, the outer guard only
    covers unexpected failures (e.g. task serialisation / DB errors) so a task
    never leaves an execution stuck in ``running``.
    """
    try:
        return run_execution(execution_id)
    except Exception as exc:  # noqa: BLE001 - task must not explode
        logger.exception("performance.execute_scenario failed for %s", execution_id)
        from django.utils import timezone

        from apps.performance.models import PerformanceExecution

        PerformanceExecution.objects.filter(pk=execution_id).update(
            status="error",
            error_message=str(exc)[:2000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return execution_id
