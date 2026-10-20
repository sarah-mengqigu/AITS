"""Celery tasks for the Web UI 测试 module (ARCHITECTURE §1.7).

Tasks always receive an existing execution id so the API can return a
``task_id`` immediately; the actual run is idempotent and records every failure
on the execution row (never leaves it in ``running``).
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.web_testing.services.execution import run_execution

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="web_testing.execute_suite_task")
def execute_suite_task(self, execution_id):
    """Execute a suite execution record created by the API/scheduler."""
    logger.info("web_testing.execute_suite_task start execution=%s", execution_id)
    return run_execution(execution_id)


@shared_task(bind=True, name="web_testing.execute_case_task")
def execute_case_task(self, execution_id, case_id=None):
    """Execute a single case execution record."""
    logger.info("web_testing.execute_case_task start execution=%s case=%s",
                execution_id, case_id)
    return run_execution(execution_id, case_id=case_id)
