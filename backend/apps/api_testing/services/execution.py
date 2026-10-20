"""Execution orchestration for API suites and single cases.

Public entrypoints (imported by ``apps.scheduled_tasks`` and the API layer):

``execute_suite(suite_id, environment_id=None, triggered_by=None,
                trigger_type="manual") -> int``
``execute_case(test_case_id, environment_id=None, ...) -> int``
``run_execution(execution_id) -> int``

The module guarantees a terminal execution status: every exception is captured,
written to ``error_message`` and a report is produced, so a record can never be
stuck in ``running``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.api_testing.models import (
    APITestCase,
    APITestCaseExecutionDetail,
    APITestExecution,
    APITestSuite,
    APITestSuiteExecutionDetail,
)
from apps.api_testing.services.runner import get_runner
from apps.common.api.api_exception_handler import BusinessError
from apps.common.websocket.core import WebSocketMessageService
from apps.projects.models import Environment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _push(execution_id, status, progress, message):
    try:
        WebSocketMessageService.push_task_status(
            execution_id, status=status, progress=progress, message=message
        )
    except Exception:  # pragma: no cover - ws failures are never fatal
        logger.debug("push task status failed for execution %s", execution_id, exc_info=True)


def _project_settings(project) -> dict:
    value = getattr(project, "settings", None)
    return value if isinstance(value, dict) else {}


def resolve_environment(project, environment_id=None, suite=None):
    """Pick the environment: explicit id > suite default > project default."""
    if environment_id:
        environment = Environment.objects.filter(pk=environment_id, project=project).first()
        if environment is None:
            raise BusinessError(
                message="环境不存在或不属于该项目", code="not_found", status_code=404
            )
        return environment
    if suite is not None and suite.environment_id:
        return suite.environment
    return (
        Environment.objects.filter(project=project, is_default=True).first()
        or Environment.objects.filter(project=project).first()
    )


def _case_plan_item(case: APITestCase, base_url: str = "") -> dict:
    config = dict(case.request_config or {})
    if base_url and not config.get("base_url"):
        config["base_url"] = base_url
    return {
        "id": case.id,
        "test_case_id": case.id,
        "name": case.name,
        "case_type": case.case_type,
        "priority": case.priority,
        "request_config": config,
        "assertions": list(case.assertions or []),
        "extract": dict(case.extract or {}),
    }


def _suite_cases(suite: APITestSuite) -> list[APITestCase]:
    ordered_ids = suite.ordered_case_ids()
    if not ordered_ids:
        return []
    rows = APITestCase.objects.filter(
        project=suite.project, pk__in=ordered_ids, is_active=True
    ).select_related("endpoint__spec")
    by_id = {row.id: row for row in rows}
    return [by_id[case_id] for case_id in ordered_ids if case_id in by_id]


def _execution_variables(execution: APITestExecution) -> dict:
    variables: dict = {}
    project_settings = _project_settings(execution.project)
    project_vars = project_settings.get("variables")
    if isinstance(project_vars, dict):
        variables.update(project_vars)
    environment = execution.environment
    if environment is not None and isinstance(environment.variables, dict):
        variables.update(environment.variables)
    suite_config = {}
    if execution.suite_id and isinstance(execution.suite.config, dict):
        suite_config = execution.suite.config
    suite_vars = suite_config.get("variables")
    if isinstance(suite_vars, dict):
        variables.update(suite_vars)
    return variables


def _execution_base_url(execution: APITestExecution,
                        cases: list[APITestCase] | None = None) -> str:
    suite_config = execution.suite.config if execution.suite_id and isinstance(
        execution.suite.config, dict
    ) else {}
    candidates = [
        suite_config.get("base_url"),
        execution.environment.base_url if execution.environment_id else "",
        _project_settings(execution.project).get("base_url"),
    ]
    for case in cases or []:
        endpoint = getattr(case, "endpoint", None)
        spec = getattr(endpoint, "spec", None) if endpoint is not None else None
        if spec is not None and spec.base_url:
            candidates.append(spec.base_url)
            break
    if not cases and execution.project_id:
        spec = (
            execution.project.api_specifications.filter(base_url__gt="")
            .order_by("-created_at")
            .first()
        )
        if spec is not None:
            candidates.append(spec.base_url)
    for candidate in candidates:
        if candidate:
            return str(candidate).rstrip("/")
    return ""


def build_plan(execution: APITestExecution, cases: list[APITestCase]) -> dict:
    base_url = _execution_base_url(execution, cases)
    return {
        "cases": [_case_plan_item(case, base_url) for case in cases],
        "variables": _execution_variables(execution),
        "base_url": base_url,
        "config": dict(execution.suite.config or {}) if execution.suite_id else {},
    }


def _execution_payload(execution: APITestExecution) -> dict:
    return {
        "id": execution.id,
        "project_id": execution.project_id,
        "suite_id": execution.suite_id,
        "name": execution.name,
        "status": execution.status,
        "trigger_type": execution.trigger_type,
        "triggered_by_id": execution.triggered_by_id,
        "environment_id": execution.environment_id,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "duration_ms": execution.duration_ms,
        "total": execution.total,
        "passed": execution.passed,
        "failed": execution.failed,
        "skipped": execution.skipped,
        "pass_rate": execution.pass_rate,
        "summary": execution.summary,
        "error_message": execution.error_message,
    }


def write_report(execution: APITestExecution, result: dict | None = None,
                 extra: dict | None = None) -> str:
    """Persist the execution report under ``settings.REPORT_ROOT`` (unique dir)."""
    root = Path(settings.REPORT_ROOT)
    directory = root / "api-testing" / f"execution-{execution.id}-{uuid.uuid4().hex[:12]}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "execution": _execution_payload(execution),
            "summary": (result or {}).get("summary", execution.summary),
            "cases": (result or {}).get("cases", []),
            "artifacts": (result or {}).get("artifacts", {}),
        }
        if extra:
            payload.update(extra)
        path = directory / "report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
        return str(path)
    except OSError as exc:  # pragma: no cover - storage issues must not break runs
        logger.warning("failed to write report for execution %s: %s", execution.id, exc)
        return ""


def load_report(execution: APITestExecution) -> dict:
    """Read the report file, falling back to an inline report built from DB rows."""
    if execution.report_path:
        try:
            path = Path(execution.report_path)
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("report file unreadable: %s", execution.report_path, exc_info=True)
    return {
        "execution": _execution_payload(execution),
        "summary": execution.summary,
        "cases": [
            {
                "name": detail.case_name,
                "status": detail.status,
                "duration_ms": detail.duration_ms,
                "request": detail.request,
                "response": detail.response,
                "assertions": detail.assertions,
                "error_message": detail.error_message,
            }
            for detail in execution.case_details.all()
        ],
        "artifacts": {"mode": execution.summary.get("mode", "inline"), "inline": True},
    }


# ---------------------------------------------------------------------------
# creation helpers (API layer creates the record before dispatching a task)
# ---------------------------------------------------------------------------
def create_suite_execution(
    suite: APITestSuite,
    environment_id=None,
    triggered_by=None,
    trigger_type: str = "manual",
) -> APITestExecution:
    cases = _suite_cases(suite)
    if not cases:
        raise BusinessError(
            message="套件没有可执行用例，请先添加用例", code="empty_suite", status_code=400
        )
    environment = resolve_environment(suite.project, environment_id, suite=suite)
    return APITestExecution.objects.create(
        project=suite.project,
        suite=suite,
        name=f"{suite.name} - {timezone.now():%Y-%m-%d %H:%M:%S}",
        environment=environment,
        status="pending",
        trigger_type=trigger_type if trigger_type in {"manual", "scheduled", "api"} else "manual",
        triggered_by=triggered_by if getattr(triggered_by, "pk", None) else None,
        total=len(cases),
    )


def create_case_execution(
    test_case: APITestCase,
    environment_id=None,
    triggered_by=None,
    trigger_type: str = "manual",
) -> APITestExecution:
    environment = resolve_environment(test_case.project, environment_id)
    return APITestExecution.objects.create(
        project=test_case.project,
        suite=None,
        name=f"{test_case.name} - {timezone.now():%Y-%m-%d %H:%M:%S}",
        environment=environment,
        status="pending",
        trigger_type=trigger_type if trigger_type in {"manual", "scheduled", "api"} else "manual",
        triggered_by=triggered_by if getattr(triggered_by, "pk", None) else None,
        total=1,
        summary={"test_case_id": test_case.id, "case_name": test_case.name, "suite_id": None},
    )


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------
def _persist_case_details(execution, cases, results) -> None:
    case_map = {case.id: case for case in cases}
    details = []
    for index, item in enumerate(results):
        case_id = item.get("test_case_id") or item.get("id")
        case = case_map.get(case_id)
        details.append(
            APITestCaseExecutionDetail(
                execution=execution,
                test_case=case,
                case_name=str(item.get("name") or (case.name if case else "未命名用例")),
                status=str(item.get("status") or "error"),
                duration_ms=int(item.get("duration_ms") or 0),
                request=item.get("request") or {},
                response=item.get("response") or {},
                assertions=item.get("assertions") or [],
                error_message=str(item.get("error_message") or ""),
                step_log=item.get("step_log") or [],
                order=index,
            )
        )
    if details:
        APITestCaseExecutionDetail.objects.bulk_create(details)


def _persist_suite_detail(execution, cases, results) -> None:
    APITestSuiteExecutionDetail.objects.create(
        execution=execution,
        suite=execution.suite,
        suite_name=execution.suite.name if execution.suite_id else execution.name,
        status=execution.status,
        total=execution.total,
        passed=execution.passed,
        failed=execution.failed,
        duration_ms=execution.duration_ms,
        detail={
            "summary": execution.summary,
            "cases": [
                {
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "duration_ms": item.get("duration_ms"),
                }
                for item in results
            ],
        },
    )


def run_execution(execution_id) -> int:
    """Execute an already created APITestExecution record (idempotent)."""
    execution = (
        APITestExecution.objects.select_related("project", "suite", "environment")
        .filter(pk=execution_id)
        .first()
    )
    if execution is None:
        raise BusinessError(message="执行记录不存在", code="not_found", status_code=404)
    if execution.status == "cancelled":
        return execution.id

    execution.case_details.all().delete()
    execution.suite_details.all().delete()
    execution.status = "running"
    execution.started_at = timezone.now()
    execution.finished_at = None
    execution.error_message = ""
    execution.duration_ms = 0
    execution.save(
        update_fields=["status", "started_at", "finished_at", "error_message",
                       "duration_ms", "updated_at"]
    )
    _push(execution.id, "running", 1, "开始执行")

    started = time.perf_counter()
    cases: list[APITestCase] = []
    result: dict = {}
    try:
        if execution.suite_id:
            cases = _suite_cases(execution.suite)
        else:
            # Single case executions store their case id in summary at creation time.
            case_id = (execution.summary or {}).get("test_case_id")
            if case_id:
                test_case = APITestCase.objects.filter(pk=case_id).first()
                if test_case is not None:
                    cases = [test_case]
        execution.total = len(cases)
        execution.save(update_fields=["total", "updated_at"])

        plan = build_plan(execution, cases)

        def on_progress(progress: int, message: str):
            _push(execution.id, "running", min(99, max(1, int(progress * 0.95) + 2)), message)

        runner = get_runner()
        result = runner.run(plan, on_progress=on_progress)
        summary = result.get("summary") or {}
        status = result.get("status") or "error"
        if status not in {"passed", "failed", "error"}:
            status = "error"
        execution.status = status
        execution.total = int(summary.get("total", execution.total) or 0)
        execution.passed = int(summary.get("passed", 0) or 0)
        execution.failed = int(summary.get("failed", 0) or 0)
        execution.skipped = int(summary.get("skipped", 0) or 0)
        execution.pass_rate = float(summary.get("pass_rate", 0.0) or 0.0)
        execution.duration_ms = int(summary.get("duration_ms", 0) or 0)
        execution.finished_at = timezone.now()
        merged_summary = dict(execution.summary or {})
        merged_summary.update(
            {
                "total": execution.total,
                "passed": execution.passed,
                "failed": execution.failed,
                "skipped": execution.skipped,
                "pass_rate": execution.pass_rate,
                "duration_ms": execution.duration_ms,
                "mode": summary.get("mode", getattr(runner, "mode", "simulated")),
                "errors": int(summary.get("errors", 0) or 0),
                "suite_id": execution.suite_id,
                "case_ids": [case.id for case in cases],
            }
        )
        execution.summary = merged_summary
        if execution.status == "failed":
            execution.error_message = "；".join(
                f"{item.get('name')}: {item.get('error_message')}"
                for item in result.get("cases", [])
                if item.get("status") == "failed" and item.get("error_message")
            )[:2000]
        execution.save(
            update_fields=[
                "status", "total", "passed", "failed", "skipped", "pass_rate",
                "duration_ms", "finished_at", "summary", "error_message", "updated_at",
            ]
        )
        _persist_case_details(execution, cases, result.get("cases") or [])
        try:
            _persist_suite_detail(execution, cases, result.get("cases") or [])
        except Exception:  # pragma: no cover - suite detail is auxiliary
            logger.warning("failed to persist suite detail for %s", execution.id, exc_info=True)
        execution.report_path = write_report(execution, result)
        execution.save(update_fields=["report_path", "updated_at"])
        _push(
            execution.id,
            execution.status,
            100,
            f"执行完成：{execution.status}，通过率 {execution.pass_rate}%",
        )
    except Exception as exc:  # noqa: BLE001 - never leave a running record behind
        logger.exception("execution %s failed", execution.id)
        execution.status = "error"
        execution.error_message = str(exc)[:2000]
        execution.finished_at = timezone.now()
        execution.duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            execution.save(
                update_fields=["status", "error_message", "finished_at", "duration_ms",
                               "updated_at"]
            )
            execution.report_path = write_report(execution, result)
            execution.save(update_fields=["report_path", "updated_at"])
        except Exception:  # pragma: no cover
            logger.exception("failed to persist error state for execution %s", execution.id)
        _push(execution.id, "error", 100, f"执行异常: {exc}")

    return execution.id


def execute_suite(
    suite_id,
    environment_id=None,
    triggered_by=None,
    trigger_type: str = "manual",
) -> int:
    """Create and execute a suite run; returns ``APITestExecution.id``."""
    suite = (
        APITestSuite.objects.select_related("project", "environment")
        .filter(pk=suite_id)
        .first()
    )
    if suite is None:
        raise BusinessError(message="测试套件不存在", code="not_found", status_code=404)
    execution = create_suite_execution(
        suite,
        environment_id=environment_id,
        triggered_by=triggered_by,
        trigger_type=trigger_type,
    )
    return run_execution(execution.id)


def execute_case(
    test_case_id,
    environment_id=None,
    triggered_by=None,
    trigger_type: str = "manual",
) -> int:
    """Create and execute a single test case; returns ``APITestExecution.id``."""
    test_case = (
        APITestCase.objects.select_related("project", "endpoint")
        .filter(pk=test_case_id)
        .first()
    )
    if test_case is None:
        raise BusinessError(message="测试用例不存在", code="not_found", status_code=404)
    execution = create_case_execution(
        test_case,
        environment_id=environment_id,
        triggered_by=triggered_by,
        trigger_type=trigger_type,
    )
    return run_execution(execution.id)
