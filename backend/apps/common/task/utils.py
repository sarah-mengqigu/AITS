"""Celery task helpers shared by execution modules."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from django.utils import timezone

from apps.common.websocket.core import WebSocketMessageService

logger = logging.getLogger(__name__)


def submit(task, *args, **kwargs):
    """Run a Celery task, degrading gracefully to a local call.

    In test / offline mode Celery is eager already, but we also protect against
    a misconfigured broker so that API calls never explode.
    """
    try:
        return task.delay(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - broker unavailable
        logger.warning("celery dispatch failed (%s), running inline", exc)
        return task.apply(args=args, kwargs=kwargs)


def push_progress(task_id, status, progress=0, message="", extra=None):
    WebSocketMessageService.push_task_status(
        task_id, status=status, progress=progress, message=message, extra=extra
    )


@contextmanager
def task_lifecycle(task_id, start_message="任务开始"):
    push_progress(task_id, "running", 1, start_message)
    try:
        yield
    except Exception as exc:
        logger.exception("task %s failed", task_id)
        push_progress(task_id, "failed", 100, str(exc))
        raise
    finally:
        pass


def now():
    return timezone.now()
