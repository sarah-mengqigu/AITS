"""Celery tasks for the 移动端 App 测试 module (ARCHITECTURE §1.7).

The API creates the :class:`~apps.app_testing.models.AppTestRun` row first (so a
``run_id``/``task_id`` can be returned immediately) and then dispatches these
tasks. Tasks are idempotent and every failure is persisted on the run row.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.app_testing.services.execution import execute_run

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="app_testing.execute_suite_task")
def execute_suite_task(self, run_id):
    """Execute an existing suite run."""
    logger.info("app_testing.execute_suite_task start run=%s", run_id)
    return execute_run(run_id)


@shared_task(bind=True, name="app_testing.execute_case_task")
def execute_case_task(self, run_id, case_id=None):
    """Execute an existing one-off case run."""
    logger.info("app_testing.execute_case_task start run=%s case=%s", run_id, case_id)
    return execute_run(run_id, case_id=case_id)
