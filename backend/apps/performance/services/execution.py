"""Performance execution orchestration (``ARCHITECTURE`` §2.6).

Fixed entry point used by ``scheduled_tasks`` / the HTTP layer::

    from apps.performance.services.execution import execute_scenario
    execution_id = execute_scenario(scenario_id, config_id=None,
                                    triggered_by=None, trigger_type="manual")

The flow is: create a ``pending`` execution -> refresh Prometheus file SD ->
generate the locustfile -> run via :func:`get_runner` -> parse statistics ->
write JSON/HTML reports -> mark ``passed`` / ``failed`` -> push WebSocket
progress. Any exception is caught and recorded as ``status="error"`` so a run can
never be stuck in ``running``.
"""

from __future__ import annotations

import html
import json
import logging
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.common.api.api_exception_handler import BusinessError
from apps.common.task.utils import push_progress

from ..constants import ERROR_RATE_THRESHOLD
from ..models import (
    TRIGGER_TYPES,
    LoadConfiguration,
    PerformanceExecution,
    PerformanceScenario,
)
from .runner import get_runner
from .script_generator import build_plan
from .stats import parse_locust_csv

try:  # pragma: no cover - shared utility owned by the integration stream
    from utils.prometheus_sd import update_windows_exporter_target
except Exception:  # noqa: BLE001 - module missing must never break execution
    update_windows_exporter_target = None

logger = logging.getLogger(__name__)

MAX_REPORT_SAMPLES = 120


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _mode() -> str:
    return str(getattr(settings, "AITS_EXECUTION_MODE", "simulated") or "simulated").lower()


def _execution_name(scenario: PerformanceScenario) -> str:
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    return f"{scenario.name} {stamp}"[:255]


def _decide_status(summary: dict, runner_status: str = "") -> str:
    """Pass only when the error rate is within threshold **and** P95 exists."""
    if runner_status == "error":
        return "error"
    error_rate = float(summary.get("error_rate") or 0.0)
    p95 = int(summary.get("p95_response_time") or 0)
    if error_rate <= ERROR_RATE_THRESHOLD and p95 > 0:
        return "passed"
    return "failed"


def _sync_prometheus_target() -> dict:
    """Register the load generator host into Prometheus File SD (best effort)."""
    if not getattr(settings, "PROMETHEUS_SD_AUTO_UPDATE", True):
        return {"enabled": False, "reason": "disabled"}
    if update_windows_exporter_target is None:
        logger.warning("prometheus_sd helper unavailable, skip target update")
        return {"enabled": False, "reason": "unavailable"}
    try:
        return update_windows_exporter_target()
    except Exception as exc:  # noqa: BLE001 - monitoring is auxiliary
        logger.warning("prometheus sd update failed: %s", exc)
        return {"enabled": False, "reason": str(exc)}


def _report_root(execution_id) -> Path:
    root = Path(
        getattr(settings, "REPORT_ROOT", None)
        or (Path(getattr(settings, "MEDIA_ROOT", ".")) / "reports")
    )
    directory = root / str(execution_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _build_report(execution: PerformanceExecution, scenario: PerformanceScenario,
                  plan: dict, result: dict, summary: dict, mode: str) -> dict:
    artifacts = dict(result.get("artifacts") or {})
    return {
        "execution": {
            "id": execution.id,
            "name": execution.name,
            "status": execution.status,
            "trigger_type": execution.trigger_type,
            "project_id": execution.project_id,
            "scenario_id": execution.scenario_id,
            "config_id": execution.config_id,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
            "duration_ms": execution.duration_ms,
        },
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "source_type": scenario.source_type,
            "endpoint_count": scenario.endpoint_count,
        },
        "plan": {
            "users": plan.get("users"),
            "spawn_rate": plan.get("spawn_rate"),
            "duration_seconds": plan.get("duration_seconds"),
            "host": plan.get("host"),
            "mode": mode,
            "config_id": plan.get("config_id"),
            "script_path": artifacts.get("script_path", ""),
        },
        "summary": summary,
        "artifacts": artifacts,
        "samples": list(result.get("samples") or [])[:MAX_REPORT_SAMPLES],
        "generated_at": timezone.now().isoformat(),
    }


def _write_report_files(report: dict, summary: dict) -> tuple[Path, Path]:
    execution_id = report["execution"]["id"]
    directory = _report_root(execution_id)
    json_path = directory / "report.json"
    html_path = directory / "report.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_render_html_report(report, summary), encoding="utf-8")
    return json_path, html_path


def _render_html_report(report: dict, summary: dict) -> str:
    execution = report.get("execution") or {}
    rows = [
        ("执行 ID", execution.get("id")),
        ("执行名称", execution.get("name")),
        ("状态", execution.get("status")),
        ("触发方式", execution.get("trigger_type")),
        ("总请求数", summary.get("total_requests")),
        ("平均 TPS", summary.get("avg_tps")),
        ("P50 (ms)", summary.get("p50_response_time")),
        ("P95 (ms)", summary.get("p95_response_time")),
        ("P99 (ms)", summary.get("p99_response_time")),
        ("错误率", summary.get("error_rate")),
        ("状态码分布", json.dumps(summary.get("status_code_dist") or {}, ensure_ascii=False)),
    ]
    body = "\n".join(
        f"<tr><th>{html.escape(str(label))}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in rows
    )
    scenario = report.get("scenario") or {}
    plan = report.get("plan") or {}
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>AITS 性能测试报告 - {html.escape(str(execution.get('name') or ''))}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1f2937}"
        "table{border-collapse:collapse;margin:16px 0}"
        "th,td{border:1px solid #e5e7eb;padding:6px 14px;text-align:left}"
        "th{background:#f3f4f6}</style></head><body>"
        f"<h1>AITS 性能测试报告</h1><h3>场景：{html.escape(str(scenario.get('name') or ''))}</h3>"
        "<table>"
        f"{body}"
        "<tr><th>并发用户</th><td>" + html.escape(str(plan.get("users"))) + "</td></tr>"
        "<tr><th>持续时间(s)</th><td>" + html.escape(str(plan.get("duration_seconds"))) + "</td></tr>"
        "<tr><th>目标 Host</th><td>" + html.escape(str(plan.get("host") or "")) + "</td></tr>"
        "</table>"
        f"<p>生成时间：{html.escape(str(report.get('generated_at') or ''))}</p>"
        "</body></html>\n"
    )


def _persist_result(execution: PerformanceExecution, summary: dict, state: dict,
                    mode: str, status: str) -> None:
    execution.status = status
    execution.total_requests = int(summary.get("total_requests") or 0)
    execution.avg_tps = float(summary.get("avg_tps") or 0.0)
    execution.p50_response_time = int(summary.get("p50_response_time") or 0)
    execution.p95_response_time = int(summary.get("p95_response_time") or 0)
    execution.p99_response_time = int(summary.get("p99_response_time") or 0)
    execution.error_rate = float(summary.get("error_rate") or 0.0)
    execution.status_code_dist = summary.get("status_code_dist") or {}
    execution.csv_path = str(state.get("csv_path") or "")[:500]
    execution.report_path = str(state.get("report_path") or "")[:500]
    execution.summary = {
        **{
            key: summary.get(key)
            for key in (
                "total_requests",
                "failures",
                "avg_tps",
                "p50_response_time",
                "p95_response_time",
                "p99_response_time",
                "error_rate",
                "status_code_dist",
                "duration_seconds",
            )
        },
        "mode": mode,
        "users": state.get("users"),
        "spawn_rate": state.get("spawn_rate"),
        "duration_seconds_planned": state.get("planned_duration"),
        "host": state.get("host"),
        "artifacts": state.get("artifacts") or {},
        "aggregated": list(summary.get("aggregated") or [])[:30],
        "html_report_path": str(state.get("html_path") or ""),
    }
    execution.finished_at = timezone.now()
    execution.save()


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------
def create_execution(scenario: PerformanceScenario, config=None, triggered_by=None,
                     trigger_type: str = "manual") -> PerformanceExecution:
    """Create a ``pending`` execution row (no work started yet)."""
    valid_triggers = {choice[0] for choice in TRIGGER_TYPES}
    resolved_trigger = trigger_type if trigger_type in valid_triggers else "manual"
    config = config if config is not None else getattr(scenario, "config", None)
    execution = PerformanceExecution.objects.create(
        project=scenario.project,
        scenario=scenario,
        config=config,
        name=_execution_name(scenario),
        status="pending",
        trigger_type=resolved_trigger,
        summary={
            "mode": _mode(),
            "triggered_by": getattr(triggered_by, "id", triggered_by) or None,
        },
    )
    return execution


def run_execution(execution_id) -> int:
    """Run an already created execution and return its id (never raises)."""
    execution = (
        PerformanceExecution.objects.select_related("scenario", "project", "config")
        .filter(pk=execution_id)
        .first()
    )
    if execution is None:
        raise BusinessError(message="执行记录不存在", code="not_found", status_code=404)
    if execution.status != "pending":
        # Idempotent: a cancelled / finished execution is never restarted.
        logger.info("execution %s already in status %s", execution_id, execution.status)
        return execution.id

    scenario = execution.scenario
    config = execution.config or scenario.config
    push_progress(execution.id, "running", 1, "性能测试开始")
    execution.status = "running"
    execution.started_at = timezone.now()
    execution.save(update_fields=["status", "started_at", "updated_at"])

    runner = get_runner()
    mode = runner.mode
    state: dict = {}
    started = time.monotonic()
    try:
        prometheus_state = _sync_prometheus_target()

        plan = build_plan(scenario, config)
        plan["execution_id"] = execution.id
        state.update(
            {
                "users": plan.get("users"),
                "spawn_rate": plan.get("spawn_rate"),
                "planned_duration": plan.get("duration_seconds"),
                "host": plan.get("host"),
                "prometheus": prometheus_state,
            }
        )
        push_progress(execution.id, "running", 10, "启动压测执行器")

        def on_progress(progress: int, message: str) -> None:
            push_progress(execution.id, "running", progress, message)

        result = runner.run(plan, on_progress=on_progress)

        # A user may cancel while the runner is busy.
        execution.refresh_from_db(fields=["status"])
        if execution.status == "cancelled":
            push_progress(execution.id, "cancelled", 100, "执行已取消")
            return execution.id

        summary = result.get("summary") or {}
        artifacts = result.get("artifacts") or {}
        csv_path = artifacts.get("stats_csv") or artifacts.get("csv_path") or ""
        if not summary.get("total_requests") and csv_path:
            summary = parse_locust_csv(csv_path)
        if not summary:
            summary = {}

        status = _decide_status(summary, result.get("status", ""))
        measured_ms = max(int((time.monotonic() - started) * 1000), 1)

        execution.duration_ms = measured_ms
        execution.status = status
        execution.finished_at = timezone.now()
        report = _build_report(execution, scenario, plan, result, summary, mode)
        state.update(
            {
                "csv_path": csv_path,
                "artifacts": artifacts,
                "users": plan.get("users"),
                "spawn_rate": plan.get("spawn_rate"),
                "planned_duration": plan.get("duration_seconds"),
                "host": plan.get("host"),
            }
        )
        report["execution"]["status"] = status
        report["execution"]["duration_ms"] = measured_ms
        report["execution"]["finished_at"] = execution.finished_at.isoformat()
        json_path, html_path = _write_report_files(report, summary)
        state.update({"report_path": str(json_path), "html_path": str(html_path)})

        _persist_result(execution, summary, state, mode, status)
        push_progress(
            execution.id, status, 100,
            f"性能测试结束: {status} (错误率 {execution.error_rate:.2%})",
        )
        return execution.id
    except Exception as exc:  # noqa: BLE001 - never leave a running record
        logger.exception("performance execution %s failed", execution_id)
        try:
            execution.refresh_from_db(fields=["status"])
            if execution.status == "cancelled":
                push_progress(execution.id, "cancelled", 100, "执行已取消")
                return execution.id
            execution.status = "error"
            execution.error_message = str(exc)[:2000]
            execution.finished_at = timezone.now()
            execution.duration_ms = max(int((time.monotonic() - started) * 1000), 1)
            execution.save(
                update_fields=[
                    "status",
                    "error_message",
                    "finished_at",
                    "duration_ms",
                    "updated_at",
                ]
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to mark execution %s as error", execution_id)
            PerformanceExecution.objects.filter(pk=execution_id).update(
                status="error", error_message=str(exc)[:2000], finished_at=timezone.now()
            )
        push_progress(execution.id, "error", 100, f"性能测试异常: {exc}")
        return execution.id


def execute_scenario(scenario_id, config_id=None, triggered_by=None,
                     trigger_type: str = "manual") -> int:
    """Create **and** run a performance execution; returns ``PerformanceExecution.id``.

    This is the fixed signature consumed by ``apps.scheduled_tasks``.
    """
    scenario = PerformanceScenario.objects.select_related("project", "config").filter(
        pk=scenario_id
    ).first()
    if scenario is None:
        raise BusinessError(message="性能测试场景不存在", code="not_found", status_code=404)
    config = None
    if config_id not in (None, ""):
        config = LoadConfiguration.objects.filter(pk=config_id).first()
        if config is None:
            raise BusinessError(message="负载配置不存在", code="config_not_found", status_code=404)
    execution = create_execution(
        scenario, config=config, triggered_by=triggered_by, trigger_type=trigger_type
    )
    return run_execution(execution.id)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def load_report(execution: PerformanceExecution) -> dict:
    """Read the JSON report, falling back to an inline report from DB rows."""
    if execution.report_path:
        try:
            path = Path(execution.report_path)
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("report unreadable: %s", execution.report_path, exc_info=True)
    summary = execution.summary or {}
    return {
        "execution": {
            "id": execution.id,
            "name": execution.name,
            "status": execution.status,
            "trigger_type": execution.trigger_type,
            "project_id": execution.project_id,
            "scenario_id": execution.scenario_id,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
            "duration_ms": execution.duration_ms,
        },
        "scenario": {
            "id": execution.scenario_id,
            "name": getattr(execution.scenario, "name", ""),
            "source_type": getattr(execution.scenario, "source_type", ""),
        },
        "summary": {
            "total_requests": execution.total_requests,
            "avg_tps": execution.avg_tps,
            "p50_response_time": execution.p50_response_time,
            "p95_response_time": execution.p95_response_time,
            "p99_response_time": execution.p99_response_time,
            "error_rate": execution.error_rate,
            "status_code_dist": execution.status_code_dist,
        },
        "artifacts": {
            "mode": summary.get("mode", "inline"),
            "csv_path": execution.csv_path,
            "html_report_path": summary.get("html_report_path", ""),
            "inline": True,
        },
        "samples": [],
        "generated_at": timezone.now().isoformat(),
    }
