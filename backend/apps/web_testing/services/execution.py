"""Execution orchestration for Web UI tests (ARCHITECTURE §2.4).

Fixed signatures consumed by ``scheduled_tasks`` and other modules::

    execute_suite(suite_id, environment_id=None, triggered_by=None,
                  trigger_type="manual") -> int   # WebUITestExecution.id
    execute_case(case_id, environment_id=None) -> int
    run_execution(execution_id) -> int

Guarantees
----------
* The execution record always leaves the ``running`` state: any failure is
  recorded as ``status="error"`` with ``error_message`` and ``finished_at``.
* Per case details, an HTML/JSON report under ``settings.REPORT_ROOT`` and an
  Allure results directory are produced for every non-crashing run.
* Progress is pushed over WebSocket (``WebSocketMessageService``); a broken
  channel layer never breaks the execution.
"""

from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.common.api.api_exception_handler import BusinessError
from apps.common.websocket.core import WebSocketMessageService
from apps.web_testing.models import (
    WebUITestCase,
    WebUITestCaseExecutionDetail,
    WebUITestExecution,
    WebUITestSuite,
)
from apps.web_testing.services.runner import get_runner
from apps.web_testing.services.script_builder import generate_playwright_script

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def report_root() -> Path:
    root = getattr(settings, "REPORT_ROOT", None)
    if root is None:  # pragma: no cover - settings always defines it
        root = Path(settings.MEDIA_ROOT) / "reports"
    return Path(root)


def _safe_relpath(path) -> str:
    """Turn an absolute artefact path into a media relative path when possible."""
    raw = str(path or "")
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if media_root and raw.startswith(media_root):
        return raw[len(media_root):].lstrip("/")
    return raw


def _push_status(execution: WebUITestExecution, status: str, progress: int, message: str,
                 extra: dict | None = None) -> None:
    try:
        WebSocketMessageService.push_task_status(
            execution.id, status=status, progress=progress, message=message,
            extra=extra or {"execution_id": execution.id},
        )
    except Exception:  # pragma: no cover - ws must never break execution
        logger.debug("websocket push failed for execution %s", execution.id, exc_info=True)


def _record_metrics(status: str, cases: list) -> None:
    try:
        from apps.common.metrics import record_case, record_execution

        record_execution("web", status)
        for case in cases:
            record_case("web", case.get("status", "passed"))
    except Exception:  # pragma: no cover - metrics are optional
        logger.debug("metrics recording failed", exc_info=True)


def _resolve_cases(execution: WebUITestExecution, case_id=None) -> list[WebUITestCase]:
    """Resolve which cases belong to this execution."""
    if case_id is not None:
        case = WebUITestCase.objects.filter(pk=case_id, project_id=execution.project_id).first()
        return [case] if case else []
    ids = []
    summary_ids = (execution.summary or {}).get("case_ids") or []
    if summary_ids:
        ids = [int(cid) for cid in summary_ids]
    elif execution.suite_id:
        ids = [int(cid) for cid in (execution.suite.case_ids or []) if cid is not None]
    if not ids:
        return []
    cases = {
        case.id: case
        for case in WebUITestCase.objects.filter(
            project_id=execution.project_id, id__in=ids
        ).select_related("project")
    }
    return [cases[cid] for cid in ids if cid in cases]


def _case_payload(case: WebUITestCase, mode: str) -> dict:
    script = case.script or ""
    if mode == "real" and not script.strip():
        try:
            script = generate_playwright_script(case)
        except Exception:  # pragma: no cover - generation must not break execution
            logger.warning("script generation failed for case %s", case.id, exc_info=True)
            script = ""
    return {
        "case_id": case.id,
        "name": case.name,
        "steps": case.steps or [],
        "assertions": case.assertions or [],
        "script": script,
        "script_type": case.script_type,
    }


def _build_plan(execution: WebUITestExecution, cases: list[WebUITestCase],
                mode: str) -> dict:
    return {
        "execution_id": execution.id,
        "project_id": execution.project_id,
        "suite_id": execution.suite_id,
        "browser": execution.browser,
        "headless": True,
        "mode": mode,
        "cases": [_case_payload(case, mode) for case in cases],
    }


def _write_report(execution: WebUITestExecution, report: dict) -> tuple[Path, Path]:
    """Write JSON + HTML reports under ``REPORT_ROOT/<execution_id>/``."""
    directory = report_root() / str(execution.id)
    os.makedirs(directory, exist_ok=True)
    json_path = directory / "report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = directory / "report.html"
    html_path.write_text(_render_html_report(execution, report), encoding="utf-8")
    return json_path, html_path


def _render_html_report(execution: WebUITestExecution, report: dict) -> str:
    summary = report.get("summary") or {}
    rows = []
    for case in report.get("cases") or []:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(case.get('name', '')))}</td>"
            f"<td>{html.escape(str(case.get('status', '')))}</td>"
            f"<td>{case.get('duration_ms', 0)}</td>"
            f"<td>{html.escape(str(case.get('error_message', '')))}</td>"
            "</tr>"
        )
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>Web UI 测试报告 - {html.escape(execution.name)}</title>"
        "<style>body{font-family:system-ui,-apple-system,sans-serif;margin:24px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;"
        "padding:8px;font-size:13px}th{background:#f5f7fa;text-align:left}"
        ".ok{color:#2e7d32}.fail{color:#c62828}</style></head><body>"
        f"<h2>Web UI 测试报告</h2><p>执行: {html.escape(execution.name)} "
        f"(id={execution.id})</p><p>状态: {html.escape(str(report.get('status', '')))} "
        f"| 总数 {summary.get('total', 0)} | 通过 {summary.get('passed', 0)} "
        f"| 失败 {summary.get('failed', 0)} | 跳过 {summary.get('skipped', 0)} "
        f"| 通过率 {summary.get('pass_rate', 0)}%</p>"
        "<table><thead><tr><th>用例</th><th>状态</th><th>耗时(ms)</th>"
        "<th>错误</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )


def _persist_details(execution: WebUITestExecution, cases: list[dict]) -> None:
    """Replace the execution details with the results of this run (idempotent)."""
    execution.details.all().delete()
    details = []
    for item in cases:
        step_log = item.get("step_log") or item.get("steps") or []
        details.append(
            WebUITestCaseExecutionDetail(
                execution=execution,
                test_case_id=item.get("case_id"),
                case_name=item.get("name") or "",
                status=item.get("status") or "error",
                duration_ms=int(item.get("duration_ms") or 0),
                steps=step_log,
                step_log=step_log,
                screenshots=item.get("screenshots") or [],
                error_message=item.get("error_message") or "",
            )
        )
    if details:
        WebUITestCaseExecutionDetail.objects.bulk_create(details)


# ---------------------------------------------------------------------------
# core execution
# ---------------------------------------------------------------------------
def run_execution(execution_id: int, case_id=None) -> int:
    """Execute an existing :class:`WebUITestExecution` record; never leaves running."""
    execution = (
        WebUITestExecution.objects.select_related("project", "suite")
        .filter(pk=execution_id)
        .first()
    )
    if execution is None:
        raise BusinessError(message="执行记录不存在", code="not_found", status_code=404)

    if execution.status in ("passed", "failed", "error", "cancelled"):
        # Idempotency: a finished/cancelled execution is never re-run.
        return execution.id

    from apps.web_testing.services.runner import execution_mode

    mode = execution_mode()
    cases = _resolve_cases(execution, case_id=case_id)
    started = timezone.now()
    execution.status = "running"
    execution.started_at = started
    execution.finished_at = None
    execution.error_message = ""
    execution.summary = {
        **(execution.summary or {}),
        "case_ids": [case.id for case in cases],
        "mode": mode,
    }
    execution.save(
        update_fields=["status", "started_at", "finished_at", "error_message", "summary",
                       "updated_at"]
    )
    _push_status(execution, "running", 1, "执行开始")

    def on_progress(percent: int, message: str) -> None:
        _push_status(execution, "running", percent, message)

    try:
        plan = _build_plan(execution, cases, mode)
        runner = get_runner(
            mode, execution_id=execution.id, browser=execution.browser, headless=True
        )
        report = runner.run(plan, on_progress=on_progress)
        _apply_report(execution, report, started, cases)
        _push_status(
            execution, execution.status, 100,
            f"执行完成: {execution.status}", {"execution_id": execution.id},
        )
        _record_metrics(execution.status, report.get("cases") or [])
    except Exception as exc:  # noqa: BLE001 - every failure must be persisted
        logger.exception("web_testing execution %s failed", execution.id)
        finished = timezone.now()
        execution.status = "error"
        execution.error_message = str(exc) or exc.__class__.__name__
        execution.finished_at = finished
        execution.duration_ms = max(int((finished - started).total_seconds() * 1000), 1)
        execution.summary = {
            **(execution.summary or {}),
            "mode": mode,
            "error_type": exc.__class__.__name__,
            "artifacts": {},
        }
        execution.save(
            update_fields=["status", "error_message", "finished_at", "duration_ms",
                           "summary", "updated_at"]
        )
        try:
            _write_report(execution, {
                "status": "error",
                "error_message": execution.error_message,
                "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0,
                            "pass_rate": 0.0},
                "cases": [],
            })
        except Exception:  # pragma: no cover - report writing is best effort
            logger.warning("failed to write error report", exc_info=True)
        _push_status(execution, "error", 100, execution.error_message,
                     {"execution_id": execution.id})
        _record_metrics("error", [])
        _safe_callback(execution)
    return execution.id


def _apply_report(execution: WebUITestExecution, report: dict, started, cases) -> None:
    """Persist details, artefacts and statuses from a runner report."""
    finished = timezone.now()
    summary = dict(report.get("summary") or {})
    case_results = list(report.get("cases") or [])
    artifacts = report.get("artifacts") or {}

    _persist_details(execution, case_results)

    allure_path = artifacts.get("allure_results_path") or ""
    report_payload = {
        "execution_id": execution.id,
        "name": execution.name,
        "status": report.get("status", "error"),
        "browser": execution.browser,
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "cases": case_results,
        "artifacts": artifacts,
    }
    json_path, html_path = _write_report(execution, report_payload)

    execution.status = report.get("status") or "error"
    execution.total = int(summary.get("total") or len(case_results))
    execution.passed = int(summary.get("passed") or 0)
    execution.failed = int(summary.get("failed") or 0)
    execution.skipped = int(summary.get("skipped") or 0)
    execution.pass_rate = float(summary.get("pass_rate") or 0.0)
    execution.finished_at = finished
    execution.duration_ms = max(int((finished - started).total_seconds() * 1000), 1)
    execution.report_path = str(html_path)
    execution.allure_results_path = str(allure_path)
    execution.summary = {
        **(execution.summary or {}),
        **summary,
        "report_json": str(json_path),
        "report_html": str(html_path),
        "report_url": _safe_relpath(html_path),
        "allure_results_path": str(allure_path),
        "case_ids": [case.id for case in cases],
        "artifacts": artifacts,
    }
    execution.error_message = "；".join(
        item.get("error_message", "") for item in case_results
        if item.get("status") in ("failed", "error") and item.get("error_message")
    )[:2000]
    execution.save()
    _safe_callback(execution)


def _safe_callback(execution: WebUITestExecution) -> None:
    """Notify ``scheduled_tasks``/notifications hooks when installed (optional)."""
    try:
        from apps.scheduled_tasks.signals import on_execution_finished  # type: ignore
    except Exception:
        return
    try:
        on_execution_finished("web", execution)
    except Exception:  # pragma: no cover - optional integration
        logger.debug("execution finished callback failed", exc_info=True)


# ---------------------------------------------------------------------------
# creation entrypoints (fixed signatures)
# ---------------------------------------------------------------------------
def _create_execution(project, name, suite=None, case_ids=None, environment_id=None,
                      triggered_by=None, trigger_type="manual", browser="chromium",
                      summary=None) -> WebUITestExecution:
    return WebUITestExecution.objects.create(
        project=project,
        suite=suite,
        name=name,
        status="pending",
        trigger_type=trigger_type or "manual",
        triggered_by=triggered_by,
        browser=browser or "chromium",
        summary={
            **(summary or {}),
            "case_ids": list(case_ids or []),
            "environment_id": environment_id,
        },
    )


def execute_suite(suite_id, environment_id=None, triggered_by=None,
                  trigger_type="manual") -> int:
    """Create + run an execution for a suite; returns the execution id.

    This is the fixed entrypoint used by ``apps.scheduled_tasks``.
    """
    suite = WebUITestSuite.objects.select_related("project").filter(pk=suite_id).first()
    if suite is None:
        raise BusinessError(message="测试套件不存在", code="not_found", status_code=404)
    if environment_id is None and suite.environment_id:
        environment_id = suite.environment_id
    case_ids = [cid for cid in (suite.case_ids or []) if cid is not None]
    execution = _create_execution(
        project=suite.project,
        name=f"{suite.name} - {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
        suite=suite,
        case_ids=case_ids,
        environment_id=environment_id,
        triggered_by=triggered_by,
        trigger_type=trigger_type,
        browser=suite.browser,
        summary={"suite_name": suite.name, "case_count": len(case_ids)},
    )
    _push_status(execution, "pending", 0, "执行已排队")
    return run_execution(execution.id)


def execute_case(case_id, environment_id=None, triggered_by=None,
                 trigger_type="manual") -> int:
    """Create + run an execution for a single case; returns the execution id."""
    case = WebUITestCase.objects.select_related("project").filter(pk=case_id).first()
    if case is None:
        raise BusinessError(message="测试用例不存在", code="not_found", status_code=404)
    execution = _create_execution(
        project=case.project,
        name=f"{case.name} - {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
        case_ids=[case.id],
        environment_id=environment_id,
        triggered_by=triggered_by,
        trigger_type=trigger_type,
        summary={"single_case": True, "case_name": case.name, "case_ids": [case.id]},
    )
    _push_status(execution, "pending", 0, "执行已排队")
    return run_execution(execution.id, case_id=case.id)


def create_suite_execution(suite, triggered_by=None, trigger_type="manual",
                           environment_id=None) -> WebUITestExecution:
    """Create (but do not run) a pending suite execution - used by views/tasks."""
    case_ids = [cid for cid in (suite.case_ids or []) if cid is not None]
    if environment_id is None and suite.environment_id:
        environment_id = suite.environment_id
    execution = _create_execution(
        project=suite.project,
        name=f"{suite.name} - {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
        suite=suite,
        case_ids=case_ids,
        environment_id=environment_id,
        triggered_by=triggered_by,
        trigger_type=trigger_type,
        browser=suite.browser,
        summary={"suite_name": suite.name, "case_count": len(case_ids)},
    )
    _push_status(execution, "pending", 0, "执行已排队")
    return execution


def create_case_execution(case, triggered_by=None, trigger_type="manual",
                          environment_id=None) -> WebUITestExecution:
    """Create (but do not run) a pending single case execution."""
    execution = _create_execution(
        project=case.project,
        name=f"{case.name} - {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
        case_ids=[case.id],
        environment_id=environment_id,
        triggered_by=triggered_by,
        trigger_type=trigger_type,
        summary={"single_case": True, "case_name": case.name, "case_ids": [case.id]},
    )
    _push_status(execution, "pending", 0, "执行已排队")
    return execution
