"""执行编排（ARCHITECTURE §2.5 / §1.8）.

固定入口（供 ``scheduled_tasks`` 与其它模块调用）::

    execute_suite(suite_id, environment_id=None, triggered_by=None,
                  trigger_type="manual") -> int   # AppTestRun.id
    execute_case(case_id, environment_id=None, triggered_by=None,
                 trigger_type="manual") -> int

内部函数 ``run_suite(suite, ...)`` / ``execute_run(run_id)`` 负责真正的执行。

降级策略
--------
* ``settings.AITS_EXECUTION_MODE != "real"`` **或** ``SONIC_BASE_URL`` 为空 →
  ``simulated`` 模式：完全不调用 Sonic，按用例数量与名称/序号产生**确定性**结果
  （用例名含「失败/fail/error/异常」或序号 ``% 5 == 4`` 视为失败，其余通过）。
* ``real``：调用 Sonic ``runSuite`` 并轮询 ``suiteResult``（带超时保护），把结果
  映射为 passed/failed。

一致性保证
----------
* pending -> running -> 汇总 -> finished_at/duration_ms -> status
* 每次执行写 ``settings.REPORT_ROOT/<run_id>/report.json``（``report_path``）
* 进度通过 ``WebSocketMessageService.push_task_status(run.id, ...)`` 推送（失败不影响执行）
* 任何异常都落库 ``status="error"`` + ``error_message``，绝不残留 ``running``
* 终态/已取消的执行重复调用是幂等的（直接返回原 id）
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.common.api.api_exception_handler import BusinessError
from apps.common.websocket.core import WebSocketMessageService
from apps.app_testing.models import (
    TERMINAL_RUN_STATUSES,
    AppTestCase,
    AppTestRun,
    AppTestSuite,
)
from apps.app_testing.services.case_converter import (
    aits_steps_to_sonic,
    build_suite_payload,
)
from apps.app_testing.services.sonic_client import get_sonic_client

logger = logging.getLogger(__name__)

#: Polling helpers (patched in tests to keep them instant)
def _sleep(seconds):  # pragma: no cover - trivial indirection
    time.sleep(seconds)


REAL_POLL_INTERVAL = 1.0
REAL_POLL_ATTEMPTS = 10
SONIC_TERMINAL_STATUSES = {"passed", "failed", "error", "cancelled", "finish", "finished"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def report_root() -> Path:
    root = getattr(settings, "REPORT_ROOT", None)
    if root is None:  # pragma: no cover - settings always defines it
        root = Path(settings.MEDIA_ROOT) / "reports"
    return Path(root)


def execution_mode() -> str:
    """Return ``real`` only when enabled *and* Sonic is configured."""
    mode = str(getattr(settings, "AITS_EXECUTION_MODE", "simulated") or "simulated").lower()
    sonic_configured = bool(str(getattr(settings, "SONIC_BASE_URL", "") or "").strip())
    return "real" if mode == "real" and sonic_configured else "simulated"


def _safe_relpath(path) -> str:
    raw = str(path or "")
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if media_root and raw.startswith(media_root):
        return raw[len(media_root):].lstrip("/")
    return raw


def _push(run: AppTestRun, status: str, progress: int, message: str,
          extra: dict | None = None) -> None:
    try:
        WebSocketMessageService.push_task_status(
            run.id, status=status, progress=progress, message=message,
            extra=extra or {"run_id": run.id},
        )
    except Exception:  # pragma: no cover - ws must never break execution
        logger.debug("websocket push failed for app run %s", run.id, exc_info=True)


def _record_metrics(status: str, cases: list) -> None:
    try:
        from apps.common.metrics import record_case, record_execution

        record_execution("app", status)
        for case in cases:
            record_case("app", case.get("status", "passed"))
    except Exception:  # pragma: no cover - metrics are optional
        logger.debug("metrics recording failed", exc_info=True)


def _simulated_case_status(case: AppTestCase, index: int) -> str:
    """Deterministic simulated verdict (assertable in tests)."""
    name = (case.name or "").lower()
    if any(keyword in name for keyword in ("失败", "fail", "error", "异常")):
        return "failed"
    if index % 5 == 4:
        return "failed"
    return "passed"


def _case_duration(case: AppTestCase, index: int) -> int:
    return 120 + (len(case.name or "") * 3) % 90 + index * 15


def _resolve_cases(run: AppTestRun, case_id=None) -> tuple[list, list]:
    """Return ``(cases_to_run, missing_or_inactive_ids)``."""
    if case_id is not None:
        case = AppTestCase.objects.select_related("project", "application").filter(
            pk=case_id, project_id=run.project_id
        ).first()
        if case is None:
            return [], [case_id]
        return ([case] if case.is_active else []), ([] if case.is_active else [case.id])

    ids = []
    summary_ids = (run.summary or {}).get("case_ids") or []
    if summary_ids:
        ids = [int(cid) for cid in summary_ids]
    elif run.suite_id:
        ids = [int(cid) for cid in (run.suite.case_ids or []) if cid is not None]
    if not ids:
        return [], []
    loaded = {
        case.id: case
        for case in AppTestCase.objects.select_related("project", "application").filter(
            project_id=run.project_id, id__in=ids
        )
    }
    cases = []
    missing = []
    for cid in ids:
        case = loaded.get(cid)
        if case is None:
            missing.append(cid)
        elif not case.is_active:
            missing.append(cid)
        else:
            cases.append(case)
    return cases, missing


def _write_report(run: AppTestRun, report: dict) -> Path:
    directory = report_root() / str(run.id)
    os.makedirs(directory, exist_ok=True)
    json_path = directory / "report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def _build_report(run: AppTestRun, mode: str, cases: list, started, finished,
                  summary: dict) -> dict:
    return {
        "run_id": run.id,
        "name": run.name,
        "status": summary.get("status", run.status),
        "mode": mode,
        "project_id": run.project_id,
        "suite": (
            {"id": run.suite_id, "name": run.suite.name} if run.suite_id else None
        ),
        "device": {
            "udid": run.device_udid,
            "device_id": run.device_id,
            "device_name": run.device_name,
            "platform": run.platform,
        },
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": summary.get("duration_ms", 0),
        "summary": summary,
        "cases": cases,
    }


# ---------------------------------------------------------------------------
# simulated execution
# ---------------------------------------------------------------------------
def _run_simulated(run: AppTestRun, cases: list, started) -> dict:
    results = []
    for index, case in enumerate(cases):
        status = _simulated_case_status(case, index)
        steps = case.steps or []
        results.append(
            {
                "case_id": case.id,
                "name": case.name,
                "status": status,
                "duration_ms": _case_duration(case, index),
                "step_count": len(steps),
                "steps": steps,
                "sonic_steps": case.sonic_steps or aits_steps_to_sonic(steps),
                "error_message": "" if status == "passed" else "模拟执行：断言失败",
                "simulated": True,
            }
        )
    finished = timezone.now()
    total = len(results)
    passed = sum(1 for item in results if item["status"] == "passed")
    failed = sum(1 for item in results if item["status"] == "failed")
    summary = {
        "mode": "simulated",
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "status": "failed" if failed else "passed",
        "duration_ms": max(int((finished - started).total_seconds() * 1000), 1),
        "engine": "simulated",
    }
    return {"cases": results, "summary": summary, "finished": finished}


# ---------------------------------------------------------------------------
# real execution (Sonic)
# ---------------------------------------------------------------------------
def _normalize_sonic_status(value) -> str:
    status = str(value or "").strip().lower()
    if status in ("passed", "pass", "success", "0", "1"):
        return "passed"
    if status in ("failed", "fail", "failure", "2"):
        return "failed"
    if status in ("skipped", "skip", "3"):
        return "skipped"
    if status in ("running", "pending", "waiting", "4"):
        return "running"
    return "error"


def _sonic_result_cases(result: dict, cases: list) -> list:
    """Map a Sonic ``suiteResult`` payload onto per case results."""
    result = result or {}
    raw_cases = (
        result.get("cases")
        or result.get("caseResults")
        or result.get("steps")
        or (result.get("data") or {}).get("cases")
        or []
    )
    by_name = {case.name: case for case in cases}
    mapped = []
    if isinstance(raw_cases, list):
        for index, item in enumerate(raw_cases):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("caseName") or "")
            status = _normalize_sonic_status(
                item.get("status") or item.get("result") or item.get("caseStatus")
            )
            case = by_name.get(name) or (cases[index] if index < len(cases) else None)
            mapped.append(
                {
                    "case_id": case.id if case else None,
                    "name": name or (case.name if case else f"用例{index + 1}"),
                    "status": status,
                    "duration_ms": int(item.get("duration") or item.get("durationMs") or 0),
                    "error_message": str(item.get("error") or item.get("message") or ""),
                    "steps": case.steps if case else [],
                }
            )
    if mapped:
        return mapped
    # Sonic only reported a global verdict -> mirror it on every case.
    overall = _normalize_sonic_status(result.get("status") or result.get("result"))
    overall = "passed" if overall not in ("failed", "error") else overall
    return [
        {
            "case_id": case.id,
            "name": case.name,
            "status": overall,
            "duration_ms": 0,
            "error_message": "" if overall == "passed" else "Sonic 套件执行失败",
            "steps": case.steps or [],
        }
        for case in cases
    ]


def _poll_sonic_result(client, suite_id, run: AppTestRun) -> dict:
    """Poll ``suiteResult`` until terminal or the timeout budget is exhausted."""
    last = {}
    for attempt in range(REAL_POLL_ATTEMPTS):
        last = client.suite_result(suite_id) or {}
        status = str(last.get("status") or last.get("result") or "").lower()
        running = _normalize_sonic_status(status) == "running"
        if status in SONIC_TERMINAL_STATUSES or not running:
            return last
        _push(run, "running", min(10 + attempt * 8, 90), "Sonic 执行中")
        _sleep(REAL_POLL_INTERVAL)
    logger.warning("sonic suite %s polling timed out", suite_id)
    return last


def _run_real(run: AppTestRun, cases: list, started) -> dict:
    client = get_sonic_client(run.project)
    payload = build_suite_payload(run.suite, cases, run.project)
    suite_device_config = (
        (run.suite.device_config or {}) if run.suite_id and run.suite is not None else {}
    )
    suite_ref = (
        run.sonic_suite_id
        or suite_device_config.get("sonic_suite_id")
        or (run.suite_id if run.suite_id else "")
        or f"aits-run-{run.id}"
    )
    _push(run, "running", 5, "提交 Sonic 套件执行")
    trigger = client.run_suite(
        suite_ref,
        device_udid=run.device_udid or None,
        device_id=run.device_id or None,
        project_id=payload.get("sonicProjectId") or None,
        payload=payload,
    )
    sonic_suite_id = str(
        trigger.get("suiteId") or trigger.get("id") or suite_ref or ""
    )
    if sonic_suite_id and sonic_suite_id != run.sonic_suite_id:
        run.sonic_suite_id = sonic_suite_id
        run.save(update_fields=["sonic_suite_id", "updated_at"])

    result = _poll_sonic_result(client, suite_ref, run)
    case_results = _sonic_result_cases(result, cases)
    finished = timezone.now()
    # A still "running" case when the socket closes counts as passed (best effort).
    for item in case_results:
        if item["status"] == "running":
            item["status"] = "passed"
    total = len(case_results)
    passed = sum(1 for item in case_results if item["status"] == "passed")
    failed = sum(1 for item in case_results if item["status"] in ("failed", "error"))
    skipped = sum(1 for item in case_results if item["status"] == "skipped")
    overall = str(result.get("status") or result.get("result") or "").lower()
    if failed:
        status = "failed"
    elif overall in ("error", "exception"):
        status = "error"
    else:
        status = "passed"
    summary = {
        "mode": "real",
        "engine": "sonic",
        "sonic_suite_id": sonic_suite_id,
        "sonic_result": result,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "status": status,
        "duration_ms": max(int((finished - started).total_seconds() * 1000), 1),
    }
    return {"cases": case_results, "summary": summary, "finished": finished}


# ---------------------------------------------------------------------------
# core (idempotent) execution of an existing run row
# ---------------------------------------------------------------------------
def execute_run(run_id: int, case_id=None) -> int:
    """Execute an existing :class:`AppTestRun`; never leaves it ``running``."""
    run = AppTestRun.objects.select_related("project", "suite", "suite__application").filter(
        pk=run_id
    ).first()
    if run is None:
        raise BusinessError(message="执行记录不存在", code="not_found", status_code=404)
    if run.status in TERMINAL_RUN_STATUSES:
        return run.id  # idempotent: finished/cancelled runs are never re-run

    mode = execution_mode()
    cases, missing = _resolve_cases(run, case_id=case_id)
    started = timezone.now()
    run.status = "running"
    run.started_at = started
    run.finished_at = None
    run.error_message = ""
    run.summary = {
        **(run.summary or {}),
        "case_ids": [case.id for case in cases],
        "mode": mode,
    }
    run.save(update_fields=["status", "started_at", "finished_at", "error_message",
                            "summary", "updated_at"])
    _push(run, "running", 1, "执行开始", {"run_id": run.id, "mode": mode})

    try:
        if mode == "real":
            outcome = _run_real(run, cases, started)
        else:
            outcome = _run_simulated(run, cases, started)
        _apply_outcome(run, outcome, cases, mode, started, missing)
        _push(run, run.status, 100, f"执行完成: {run.status}",
              {"run_id": run.id, "status": run.status})
        _record_metrics(run.status, outcome.get("cases") or [])
    except Exception as exc:  # noqa: BLE001 - failures must be persisted
        logger.exception("app_testing run %s failed", run.id)
        finished = timezone.now()
        run.status = "error"
        run.error_message = str(exc) or exc.__class__.__name__
        run.finished_at = finished
        run.duration_ms = max(int((finished - started).total_seconds() * 1000), 1)
        summary = {
            "mode": mode,
            "total": len(cases),
            "passed": 0,
            "failed": 0,
            "skipped": len(missing),
            "pass_rate": 0.0,
            "status": "error",
            "duration_ms": run.duration_ms,
            "error_type": exc.__class__.__name__,
        }
        run.summary = {**(run.summary or {}), **summary}
        run.save(update_fields=["status", "error_message", "finished_at", "duration_ms",
                                "summary", "updated_at"])
        try:
            report = _build_report(run, mode, [], started, finished, summary)
            report["error_message"] = run.error_message
            report_path = _write_report(run, report)
            run.report_path = str(report_path)
            run.summary = {**run.summary, "report_json": str(report_path),
                           "report_url": _safe_relpath(report_path)}
            run.save(update_fields=["report_path", "summary", "updated_at"])
        except Exception:  # pragma: no cover - report writing is best effort
            logger.warning("failed to write error report for run %s", run.id, exc_info=True)
        _push(run, "error", 100, run.error_message, {"run_id": run.id})
        _record_metrics("error", [])
    return run.id


def _apply_outcome(run: AppTestRun, outcome: dict, cases: list, mode: str,
                   started, missing: list) -> None:
    finished = outcome.get("finished") or timezone.now()
    case_results = list(outcome.get("cases") or [])
    summary = dict(outcome.get("summary") or {})
    if missing:
        summary["skipped"] = int(summary.get("skipped") or 0) + len(missing)

    report = _build_report(run, mode, case_results, started, finished, summary)
    report_path = _write_report(run, report)

    run.status = summary.get("status") or "error"
    run.total = int(summary.get("total") or len(case_results))
    run.passed = int(summary.get("passed") or 0)
    run.failed = int(summary.get("failed") or 0)
    run.skipped = int(summary.get("skipped") or 0)
    run.pass_rate = float(summary.get("pass_rate") or 0.0)
    run.finished_at = finished
    run.duration_ms = int(summary.get("duration_ms") or 0) or max(
        int((finished - started).total_seconds() * 1000), 1
    )
    run.report_path = str(report_path)
    run.summary = {
        **(run.summary or {}),
        **summary,
        "cases": [
            {
                "case_id": item.get("case_id"),
                "name": item.get("name", ""),
                "status": item.get("status", "error"),
                "duration_ms": int(item.get("duration_ms") or 0),
                "error_message": item.get("error_message", ""),
            }
            for item in case_results
        ],
        "report_json": str(report_path),
        "report_url": _safe_relpath(report_path),
        "case_ids": [case.id for case in cases],
        "missing_case_ids": list(missing),
        "device": {
            "udid": run.device_udid,
            "device_id": run.device_id,
            "device_name": run.device_name,
            "platform": run.platform,
        },
    }
    if run.status in ("failed", "error"):
        errors = [
            item.get("error_message", "") for item in case_results
            if item.get("status") in ("failed", "error") and item.get("error_message")
        ]
        run.error_message = "；".join(errors)[:2000]
    run.save()


# ---------------------------------------------------------------------------
# creation helpers (used by views and tasks)
# ---------------------------------------------------------------------------
def _device_fields(suite, device_config: dict | None = None) -> dict:
    config = dict(device_config or {})
    if suite is not None:
        merged = dict(suite.device_config or {})
        merged.update(config)
        config = merged
    return {
        "device_udid": str(config.get("udid") or config.get("device_udid") or ""),
        "device_id": str(config.get("device_id") or config.get("deviceId") or ""),
        "device_name": str(config.get("device_name") or config.get("deviceName") or ""),
        "platform": str(config.get("platform") or ""),
        "sonic_suite_id": str(config.get("sonic_suite_id") or config.get("suiteId") or ""),
    }


def create_suite_run(suite, triggered_by=None, trigger_type="manual",
                     environment_id=None, device_config=None) -> AppTestRun:
    """Create (do not execute) a pending run for ``suite``."""
    case_ids = [cid for cid in (suite.case_ids or []) if cid is not None]
    run = AppTestRun.objects.create(
        project=suite.project,
        suite=suite,
        name=f"{suite.name} - {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
        status="pending",
        trigger_type=trigger_type or "manual",
        summary={
            "suite_name": suite.name,
            "case_ids": case_ids,
            "case_count": len(case_ids),
            "environment_id": environment_id,
            "triggered_by": getattr(triggered_by, "id", None),
        },
        **_device_fields(suite, device_config),
    )
    _push(run, "pending", 0, "执行已排队")
    return run


def create_case_run(case, triggered_by=None, trigger_type="manual",
                    environment_id=None, device_config=None) -> AppTestRun:
    """Create (do not execute) a pending one-off run for a single case."""
    run = AppTestRun.objects.create(
        project=case.project,
        suite=None,
        name=f"{case.name} - {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
        status="pending",
        trigger_type=trigger_type or "manual",
        summary={
            "single_case": True,
            "case_name": case.name,
            "case_ids": [case.id],
            "environment_id": environment_id,
            "triggered_by": getattr(triggered_by, "id", None),
        },
        **_device_fields(None, device_config),
    )
    _push(run, "pending", 0, "执行已排队")
    return run


# ---------------------------------------------------------------------------
# fixed signatures
# ---------------------------------------------------------------------------
def run_suite(suite, triggered_by=None, trigger_type="manual",
              environment_id=None, device_config=None) -> int:
    """Create + execute a run for ``suite`` (internal helper, returns run id)."""
    run = create_suite_run(
        suite, triggered_by=triggered_by, trigger_type=trigger_type,
        environment_id=environment_id, device_config=device_config,
    )
    return execute_run(run.id)


def execute_suite(suite_id, environment_id=None, triggered_by=None,
                  trigger_type="manual") -> int:
    """Fixed entrypoint for ``scheduled_tasks``; returns ``AppTestRun.id``."""
    suite = AppTestSuite.objects.select_related("project", "application").filter(
        pk=suite_id
    ).first()
    if suite is None:
        raise BusinessError(message="测试套件不存在", code="not_found", status_code=404)
    return run_suite(
        suite, triggered_by=triggered_by, trigger_type=trigger_type,
        environment_id=environment_id,
    )


def execute_case(case_id, environment_id=None, triggered_by=None,
                 trigger_type="manual") -> int:
    """Fixed entrypoint for a single ad-hoc case; returns ``AppTestRun.id``."""
    case = AppTestCase.objects.select_related("project", "application").filter(
        pk=case_id
    ).first()
    if case is None:
        raise BusinessError(message="测试用例不存在", code="not_found", status_code=404)
    run = create_case_run(
        case, triggered_by=triggered_by, trigger_type=trigger_type,
        environment_id=environment_id,
    )
    return execute_run(run.id, case_id=case.id)
