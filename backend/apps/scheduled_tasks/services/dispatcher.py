"""Execution dispatcher for scheduled tasks (ARCHITECTURE §2.8).

``dispatch_task`` is the single synchronous orchestration entrypoint:

1. load the :class:`~apps.scheduled_tasks.models.ScheduledTask`
2. create (or reuse) a ``pending`` :class:`TaskExecutionLog`, flip it to ``running``
3. for every ``suite_id`` lazily import the owning module's
   ``services.execution.execute_suite`` and run it
4. aggregate the stats, persist the log, notify receivers, then refresh the
   task's ``last_run_at`` / ``next_run_at``

Robustness rules
----------------
* a missing module (not implemented / import error) and any executor exception
  are recorded in ``step_log`` — they never escape ``dispatch_task``, so a beat
  task can never be left half executed;
* aggregation status:

  =====================================  =========
  condition                              status
  =====================================  =========
  no suite executed (all raised)         ``error``
  at least one suite raised              ``failed``
  aggregated ``failed`` > 0              ``failed``
  otherwise                              ``passed``
  =====================================  =========

* notifications are best effort: failures are stored in
  ``step_log["notification"]`` and never change the task status.
"""

from __future__ import annotations

import importlib
import logging

from django.utils import timezone as dj_timezone

from apps.scheduled_tasks.models import (
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_PENDING,
    STATUS_RUNNING,
    ScheduledTask,
    TaskExecutionLog,
)

logger = logging.getLogger(__name__)

#: ``suite_type`` -> (module path, callable name) for the execution entrypoint.
EXECUTORS: dict[str, tuple[str, str]] = {
    "api": ("apps.api_testing.services.execution", "execute_suite"),
    "web": ("apps.web_testing.services.execution", "execute_suite"),
    "app": ("apps.app_testing.services.execution", "execute_suite"),
}

#: ``suite_type`` -> (module path, model name) used to read back the stats.
EXECUTION_MODELS: dict[str, tuple[str, str]] = {
    "api": ("apps.api_testing.models", "APITestExecution"),
    "web": ("apps.web_testing.models", "WebUITestExecution"),
    "app": ("apps.app_testing.models", "AppTestRun"),
}

#: Report endpoint templates used to build ``report_urls`` (app-testing has no
#: report endpoint — ``AppTestRun.report_path`` is used instead).
REPORT_URL_TEMPLATES: dict[str, str] = {
    "api": "/api/api-testing/executions/{execution_id}/report/",
    "web": "/api/web-testing/executions/{execution_id}/report/",
}

_STAT_KEYS = ("total", "passed", "failed", "skipped")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _import_module(path: str):
    """Indirection so tests can simulate "module not implemented yet"."""
    return importlib.import_module(path)


def _as_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_executor(suite_type: str):
    """Lazily import and return ``execute_suite`` for ``suite_type``."""
    try:
        module_path, func_name = EXECUTORS[suite_type]
    except KeyError as exc:
        raise ValueError(f"不支持的套件类型: {suite_type}") from exc
    module = _import_module(module_path)
    executor = getattr(module, func_name, None)
    if not callable(executor):
        raise ImportError(f"{module_path}.{func_name} 不存在或不可调用")
    return executor


def _normalize_counts(total=None, passed=None, failed=None, skipped=None) -> dict:
    counts = {
        "total": max(_as_int(total), 0),
        "passed": max(_as_int(passed), 0),
        "failed": max(_as_int(failed), 0),
        "skipped": max(_as_int(skipped), 0),
    }
    if not counts["total"]:
        counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]
    return counts


def _pass_rate(counts: dict) -> float:
    total = counts.get("total") or 0
    if total <= 0:
        return 0.0
    return round(counts.get("passed", 0) / total * 100, 2)


def load_execution_stats(suite_type: str, execution_id) -> dict | None:
    """Read back the stats of an execution row (``None`` when it is gone)."""
    try:
        module_path, model_name = EXECUTION_MODELS[suite_type]
    except KeyError as exc:
        raise ValueError(f"不支持的套件类型: {suite_type}") from exc
    module = _import_module(module_path)
    model = getattr(module, model_name)
    row = model.objects.filter(pk=execution_id).first()
    if row is None:
        return None
    counts = _normalize_counts(
        getattr(row, "total", 0),
        getattr(row, "passed", 0),
        getattr(row, "failed", 0),
        getattr(row, "skipped", 0),
    )
    pass_rate = _as_float(getattr(row, "pass_rate", 0.0), -1.0)
    stats = {
        "execution_id": _as_int(getattr(row, "pk", execution_id)),
        "status": str(getattr(row, "status", "") or "").lower(),
        **counts,
        "pass_rate": pass_rate if pass_rate >= 0 else _pass_rate(counts),
    }
    report_path = getattr(row, "report_path", "") or ""
    template = REPORT_URL_TEMPLATES.get(suite_type, "")
    stats["report_url"] = (
        template.format(execution_id=stats["execution_id"]) if template else report_path
    )
    if report_path:
        stats["report_path"] = report_path
    return stats


def normalize_suite_result(suite_type: str, raw) -> dict:
    """Normalize an executor return value into a stats dict.

    ``execute_suite`` returns the execution id (``int``) per contract; a
    ``dict`` is also accepted (used by simulated/degraded executors and tests).
    """
    if isinstance(raw, dict):
        counts = _normalize_counts(
            raw.get("total"), raw.get("passed"), raw.get("failed"), raw.get("skipped")
        )
        status = str(raw.get("status") or "").lower()
        if status not in ("passed", "failed", "error", "cancelled", "running", "pending"):
            status = STATUS_FAILED if counts["failed"] else STATUS_PASSED
        stats = {
            "execution_id": _as_int(raw.get("execution_id") or raw.get("id"), 0) or None,
            "status": status,
            **counts,
            "pass_rate": _as_float(raw.get("pass_rate"), _pass_rate(counts)),
            "report_url": raw.get("report_url") or raw.get("report_path") or "",
        }
        return stats

    execution_id = _as_int(raw, 0)
    if not execution_id:
        raise ValueError(f"execute_suite 返回了非法的执行 ID: {raw!r}")
    stats = load_execution_stats(suite_type, execution_id)
    if stats is None:
        raise LookupError(f"执行记录不存在或不可读取: {suite_type}#{execution_id}")
    return stats


def _run_single_suite(task: ScheduledTask, suite_id, triggered_by, trigger_type) -> dict:
    """Run one suite; never raises (errors are captured in the returned step)."""
    step: dict = {
        "suite_type": task.suite_type,
        "suite_id": _as_int(suite_id),
        "status": STATUS_PENDING,
        "execution_id": None,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "pass_rate": 0.0,
        "report_url": "",
        "error": "",
    }
    try:
        executor = resolve_executor(task.suite_type)
        raw = executor(suite_id, task.environment_id, triggered_by, trigger_type)
        stats = normalize_suite_result(task.suite_type, raw)
        step.update(stats)
        step["status"] = stats.get("status") or (
            STATUS_FAILED if step["failed"] else STATUS_PASSED
        )
        if step["status"] not in ("passed", "failed", STATUS_ERROR, "cancelled"):
            step["status"] = STATUS_FAILED if step["failed"] else STATUS_PASSED
    except Exception as exc:  # import error / executor error / bad return value
        logger.warning(
            "scheduled task %s suite %s (%s) failed: %s",
            task.pk, suite_id, task.suite_type, exc,
        )
        step["status"] = STATUS_ERROR
        step["error"] = f"{type(exc).__name__}: {exc}"
    return step


def aggregate_results(steps: list[dict], suite_type: str = "") -> dict:
    """Aggregate per-suite steps into one status/stats summary."""
    executed = [step for step in steps if step.get("status") != STATUS_ERROR]
    errored = [step for step in steps if step.get("status") == STATUS_ERROR]

    counts = {key: 0 for key in _STAT_KEYS}
    for step in executed:
        for key in _STAT_KEYS:
            counts[key] += _as_int(step.get(key))

    report_urls = [
        {
            "suite_type": step.get("suite_type") or suite_type,
            "suite_id": step.get("suite_id"),
            "execution_id": step.get("execution_id"),
            "report_url": step.get("report_url") or "",
        }
        for step in executed
        if step.get("execution_id")
    ]

    errors = [str(step.get("error")) for step in steps if step.get("error")]
    if not steps:
        status = STATUS_ERROR
        errors.append("定时任务未配置任何测试套件（suite_ids 为空）")
    elif not executed:
        status = STATUS_ERROR
    elif errored or counts["failed"] > 0:
        status = STATUS_FAILED
    else:
        status = STATUS_PASSED

    failed_suites = [step for step in executed if step.get("status") == STATUS_FAILED]
    if status == STATUS_FAILED:
        if counts["failed"] > 0:
            errors.append(f"{counts['failed']} 个用例失败")
        elif failed_suites:
            errors.append(f"{len(failed_suites)} 个测试套件执行失败")

    pass_rate = (
        _pass_rate(counts) if counts["total"] > 0
        else (100.0 if status == STATUS_PASSED else 0.0)
    )
    return {
        "status": status,
        **counts,
        "pass_rate": pass_rate,
        "report_urls": report_urls,
        "error_message": "; ".join(errors)[:2000],
        "errors": errors,
        "executed_suites": len(executed),
        "errored_suites": len(errored),
    }


def _create_or_reuse_log(task, triggered_by, execution_log_id):
    if execution_log_id:
        log = TaskExecutionLog.objects.filter(pk=execution_log_id).first()
        if log is not None:
            return log
        logger.warning("execution log %s not found, creating a new one", execution_log_id)
    return TaskExecutionLog.objects.create(
        task=task,
        scheduled_task_name=task.name,
        suite_type=task.suite_type,
        status=STATUS_PENDING,
        triggered_by=triggered_by,
    )


def _notify(task, log, result) -> dict:
    """Send the notification; never raises (returned dict goes into step_log)."""
    try:
        from apps.notifications.services import trigger_notification

        outcome = trigger_notification(task, execution_log=log, result=result) or {}
        return {
            "sent": _as_int(outcome.get("sent", 0)),
            "failed": _as_int(outcome.get("failed", 0)),
            "skipped": bool(outcome.get("skipped", False)),
            "reason": str(outcome.get("reason", "") or ""),
        }
    except Exception as exc:
        logger.warning("scheduled task %s notification failed: %s", task.pk, exc)
        return {"sent": 0, "failed": 1, "skipped": False, "error": f"{type(exc).__name__}: {exc}"}


def _update_task_timestamps(task: ScheduledTask, base) -> None:
    task.last_run_at = base
    next_run = task.compute_next_run_at(base=base)
    if next_run is not None:
        task.next_run_at = next_run
    try:
        task.save(update_fields=["last_run_at", "next_run_at", "updated_at"])
    except Exception:  # pragma: no cover - defensive
        logger.warning("failed to refresh timestamps of task %s", task.pk, exc_info=True)


def _push_progress(log: TaskExecutionLog, status, progress, message):
    try:
        from apps.common.websocket.core import WebSocketMessageService

        WebSocketMessageService.push_task_status(
            log.id, status=status, progress=progress, message=message
        )
    except Exception:  # pragma: no cover - websocket is best effort
        logger.debug("ws push failed for log %s", log.id, exc_info=True)


# ---------------------------------------------------------------------------
# public entrypoint
# ---------------------------------------------------------------------------
def dispatch_task(
    task_id,
    triggered_by=None,
    trigger_type: str = "manual",
    execution_log_id=None,
) -> int | None:
    """Run every suite of task ``task_id`` and return the execution log id.

    :param task_id: :class:`ScheduledTask` primary key.
    :param triggered_by: user that triggered the run (``None`` for beat).
    :param trigger_type: ``manual`` | ``scheduled`` | ``api`` — forwarded to the
        owning modules' ``execute_suite``.
    :param execution_log_id: optional pre-created (``pending``) log id, used by
        the ``run`` API action so the returned task id stays stable.
    :returns: ``TaskExecutionLog.id``, or ``None`` when the task does not exist.
    """
    task = (
        ScheduledTask.objects.select_related("project", "environment")
        .filter(pk=task_id)
        .first()
    )
    if task is None:
        logger.warning("scheduled task %s not found, dispatch skipped", task_id)
        return None

    log = _create_or_reuse_log(task, triggered_by, execution_log_id)
    started_at = dj_timezone.now()

    log.status = STATUS_RUNNING
    log.started_at = started_at
    log.scheduled_task_name = task.name
    log.suite_type = task.suite_type
    log.error_message = ""
    log.save(update_fields=[
        "status", "started_at", "scheduled_task_name", "suite_type", "error_message",
        "updated_at",
    ])
    _push_progress(log, "running", 5, "定时任务开始执行")

    suite_ids = task.suite_id_list
    step_log: dict = {
        "trigger_type": trigger_type,
        "triggered_by": getattr(triggered_by, "id", None),
        "suite_type": task.suite_type,
        "started_at": started_at.isoformat(),
        "environment_id": task.environment_id,
        "suites": [],
        "errors": [],
    }

    steps: list[dict] = []
    for suite_id in suite_ids:
        step = _run_single_suite(task, suite_id, triggered_by, trigger_type)
        steps.append(step)
        step_log["suites"].append(step)

    summary = aggregate_results(steps, suite_type=task.suite_type)
    step_log["errors"] = summary["errors"]
    step_log["summary"] = {
        key: summary[key]
        for key in (
            "status", "total", "passed", "failed", "skipped", "pass_rate",
            "executed_suites", "errored_suites",
        )
    }

    finished_at = dj_timezone.now()
    log.status = summary["status"]
    log.total = summary["total"]
    log.passed = summary["passed"]
    log.failed = summary["failed"]
    log.skipped = summary["skipped"]
    log.pass_rate = summary["pass_rate"]
    log.report_urls = summary["report_urls"]
    log.error_message = summary["error_message"]
    log.finished_at = finished_at
    log.duration_ms = max(
        int((finished_at - started_at).total_seconds() * 1000), 0
    )
    step_log["finished_at"] = finished_at.isoformat()
    step_log["duration_ms"] = log.duration_ms
    log.step_log = step_log
    log.save()

    # notifications: best effort, the task status is already persisted.
    result = {
        "task_id": task.pk,
        "task_name": task.name,
        "execution_log_id": log.id,
        "status": log.status,
        "suite_type": task.suite_type,
        "total": log.total,
        "passed": log.passed,
        "failed": log.failed,
        "skipped": log.skipped,
        "pass_rate": log.pass_rate,
        "suites": summary["report_urls"],
    }
    step_log["notification"] = _notify(task, log, result)
    log.step_log = step_log
    log.save(update_fields=["step_log", "updated_at"])

    _update_task_timestamps(task, started_at)
    _push_progress(log, log.status, 100, f"定时任务执行完成: {log.status}")

    return log.id
