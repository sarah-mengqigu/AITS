"""Celery tasks for API suite / case execution."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.api_testing.models import APITestExecution
from apps.api_testing.services.execution import run_execution
from apps.common.task.utils import push_progress

logger = logging.getLogger(__name__)


def _mark_error(execution_id, message: str) -> None:
    try:
        APITestExecution.objects.filter(pk=execution_id).update(
            status="error",
            error_message=str(message)[:2000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to mark execution %s as error", execution_id)


@shared_task(bind=True, name="api_testing.execute_suite")
def execute_suite_task(self, execution_id):
    """Execute a suite execution record (``APITestExecution.id``)."""
    push_progress(execution_id, "running", 1, "套件执行开始")
    try:
        result = run_execution(execution_id)
        execution = APITestExecution.objects.filter(pk=execution_id).first()
        final_status = execution.status if execution is not None else "completed"
        push_progress(execution_id, final_status, 100, "套件执行结束")
        return result
    except Exception as exc:  # noqa: BLE001 - never leave a running record
        logger.exception("execute_suite_task failed for execution %s", execution_id)
        _mark_error(execution_id, exc)
        push_progress(execution_id, "error", 100, f"套件执行异常: {exc}")
        return execution_id


@shared_task(bind=True, name="api_testing.execute_case")
def execute_case_task(self, execution_id):
    """Execute a single case execution record (``APITestExecution.id``)."""
    push_progress(execution_id, "running", 1, "用例执行开始")
    try:
        result = run_execution(execution_id)
        execution = APITestExecution.objects.filter(pk=execution_id).first()
        final_status = execution.status if execution is not None else "completed"
        push_progress(execution_id, final_status, 100, "用例执行结束")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute_case_task failed for execution %s", execution_id)
        _mark_error(execution_id, exc)
        push_progress(execution_id, "error", 100, f"用例执行异常: {exc}")
        return execution_id


# Compatibility aliases used by docs / scheduled_tasks integrations.
run_suite = execute_suite_task
run_case = execute_case_task
