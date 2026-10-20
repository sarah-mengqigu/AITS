"""Execution runners for Web UI tests (ARCHITECTURE §1.8 / §2.4).

Contract
--------
``BaseRunner.run(plan, on_progress=None) -> {"status", "cases", "summary",
"artifacts"}``

* :class:`SimulatedRunner` - no browser at all: steps are evaluated with a
  deterministic rule set (``expect`` present -> compare with ``value``/``actual``,
  absent -> passed) and an Allure compatible ``<uuid>-result.json`` is written to
  ``settings.ALLURE_RESULTS_ROOT/<execution_id>/``.
* :class:`RealPlaywrightRunner` - used when ``AITS_EXECUTION_MODE=real``; drives
  Playwright through a subprocess, with an explicit availability probe so a
  missing dependency raises a clear ``RunnerUnavailable`` (mapped to an `error`
  execution record, never a hang or a silent success).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

CASE_STATUSES = ("passed", "failed", "skipped", "error")
ALLURE_STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "skipped": "skipped",
    "error": "broken",
}


class RunnerError(RuntimeError):
    """Base error for execution runners."""


class RunnerUnavailable(RunnerError):
    """Raised when the real runner cannot start (missing dependency/browser)."""


# ---------------------------------------------------------------------------
# step evaluation (deterministic, shared by all runners)
# ---------------------------------------------------------------------------
def _compare(expected, actual) -> tuple[bool, str]:
    """Deterministic expectation comparison used by the simulated runner."""
    if isinstance(expected, bool):
        matched = bool(actual) is expected
        return matched, "" if matched else f"期望 {expected}，实际 {actual!r}"
    if isinstance(expected, dict):
        for operator, operand in expected.items():
            if operator in ("contains", "contain"):
                matched = str(operand) in str(actual)
            elif operator in ("equals", "eq", "=="):
                matched = str(operand) == str(actual)
            elif operator in ("not_equals", "ne"):
                matched = str(operand) != str(actual)
            elif operator in ("visible", "exists", "truthy"):
                matched = bool(actual) is bool(operand)
            else:
                matched = str(operand) in str(actual)
            if not matched:
                return False, f"期望 {expected}，实际 {actual!r}"
        return True, ""
    if actual is None:
        return True, ""
    matched = str(expected) == str(actual)
    return matched, "" if matched else f"期望 {expected!r}，实际 {actual!r}"


def evaluate_steps(steps) -> tuple[str, list, str]:
    """Evaluate case steps deterministically.

    Returns ``(case_status, step_log, error_message)``::

        {"action": "fill", "target": "#user", "value": "admin"}      -> passed
        {"action": "assert_text", "value": "Wel", "expect": "Bye"}   -> failed
    """
    log: list[dict] = []
    errors: list[str] = []
    skipped = False
    for index, step in enumerate(steps or [], start=1):
        if not isinstance(step, dict):
            continue
        entry = {
            "index": index,
            "action": step.get("action", ""),
            "target": _short(step.get("target")),
            "value": _short(step.get("value")),
            "status": "passed",
            "message": "",
        }
        forced = str(step.get("force_status") or "").lower()
        if forced in ("skipped", "pending"):
            entry["status"] = "skipped"
            skipped = True
        elif forced in ("failed", "error"):
            entry["status"] = "failed"
            entry["message"] = str(step.get("error") or "步骤被标记为失败")
            errors.append(entry["message"])
        elif "expect" in step:
            actual = step.get("actual", step.get("value"))
            matched, message = _compare(step.get("expect"), actual)
            if not matched:
                entry["status"] = "failed"
                entry["message"] = message
                errors.append(message)
        log.append(entry)
    if errors:
        return "failed", log, "；".join(errors[:3])
    if skipped and log and all(item["status"] == "skipped" for item in log):
        return "skipped", log, ""
    return "passed", log, ""


def _short(value, limit: int = 200):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:limit]
    return str(value)[:limit]


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Base runner
# ---------------------------------------------------------------------------
class BaseRunner:
    """Common runner behaviour: plan iteration, progress, Allure artefacts."""

    name = "base"
    framework = "playwright"
    language = "python"

    def __init__(self, execution_id=None, browser="chromium", headless=True,
                 allure_root=None):
        self.execution_id = execution_id
        self.browser = browser or "chromium"
        self.headless = True if headless is None else bool(headless)
        self._allure_root = allure_root

    # -- public API --------------------------------------------------------
    def run(self, plan: dict, on_progress=None) -> dict:
        raise NotImplementedError

    # -- helpers -----------------------------------------------------------
    @property
    def allure_root(self) -> Path:
        root = self._allure_root or getattr(settings, "ALLURE_RESULTS_ROOT", None)
        if root is None:  # pragma: no cover - settings always defines it
            root = Path(settings.MEDIA_ROOT) / "allure-results"
        return Path(root)

    def results_dir(self) -> Path:
        execution_part = str(self.execution_id or "adhoc")
        path = self.allure_root / execution_part
        os.makedirs(path, exist_ok=True)
        return path

    def progress(self, on_progress, percent: int, message: str) -> None:
        if on_progress is None:
            return
        try:
            on_progress(int(percent), str(message))
        except Exception:  # pragma: no cover - progress callbacks are best effort
            logger.debug("progress callback failed", exc_info=True)

    def write_allure_result(self, case_result: dict) -> str:
        """Persist one Allure compatible ``<uuid>-result.json`` and return path."""
        directory = self.results_dir()
        uid = uuid.uuid4().hex
        start = int(case_result.get("start") or _now_ms())
        stop = int(case_result.get("stop") or start + int(case_result.get("duration_ms") or 0))
        steps = []
        for step in case_result.get("step_log") or []:
            step_start = start + 10
            steps.append(
                {
                    "name": step.get("action") or "step",
                    "status": ALLURE_STATUS_MAP.get(step.get("status", "passed"), "passed"),
                    "stage": "finished",
                    "start": step_start,
                    "stop": step_start + 5,
                    "steps": [],
                    "attachments": [],
                    "parameters": [],
                }
            )
        payload = {
            "uuid": uid,
            "historyId": f"{case_result.get('case_id') or case_result.get('name')}",
            "name": case_result.get("name") or "unnamed case",
            "fullName": f"{self.name}.{case_result.get('name') or 'case'}",
            "status": ALLURE_STATUS_MAP.get(case_result.get("status", "passed"), "passed"),
            "statusDetails": (
                {"message": case_result.get("error_message", "")}
                if case_result.get("status") in ("failed", "error")
                else {}
            ),
            "stage": "finished",
            "start": start,
            "stop": stop,
            "labels": [
                {"name": "framework", "value": self.framework},
                {"name": "language", "value": self.language},
                {"name": "browser", "value": self.browser},
                {"name": "host", "value": "aits-simulated"},
                {"name": "suite", "value": str(self.execution_id or "")},
            ],
            "steps": steps,
            "attachments": [],
            "parameters": [],
        }
        path = directory / f"{uid}-result.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def finalize(self, case_results: list, artifacts: dict) -> dict:
        total = len(case_results)
        passed = sum(1 for item in case_results if item["status"] == "passed")
        failed = sum(1 for item in case_results if item["status"] == "failed")
        skipped = sum(1 for item in case_results if item["status"] == "skipped")
        errors = sum(1 for item in case_results if item["status"] == "error")
        executed = passed + failed + errors
        pass_rate = round(passed * 100.0 / executed, 2) if executed else 0.0
        if errors:
            status = "error"
        elif failed:
            status = "failed"
        else:
            status = "passed"
        return {
            "status": status,
            "cases": case_results,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
                "pass_rate": pass_rate,
            },
            "artifacts": artifacts,
        }


# ---------------------------------------------------------------------------
# Simulated runner
# ---------------------------------------------------------------------------
class SimulatedRunner(BaseRunner):
    """Deterministic runner used for tests, demos and CI (no browser started)."""

    name = "simulated"

    def run(self, plan: dict, on_progress=None) -> dict:
        cases = list(plan.get("cases") or [])
        self.progress(on_progress, 5, "开始执行（模拟模式）")
        artifacts = {"allure_results_path": str(self.results_dir()), "result_files": []}
        case_results: list[dict] = []
        base = _now_ms()
        for index, case in enumerate(cases):
            name = case.get("name") or f"case-{index + 1}"
            duration = 100 + 20 * index
            start = base + index * 200
            status, step_log, error = evaluate_steps(case.get("steps"))
            result = {
                "case_id": case.get("case_id"),
                "name": name,
                "status": status,
                "duration_ms": duration,
                "steps": step_log,
                "step_log": step_log,
                "screenshots": [],
                "error_message": error,
                "start": start,
                "stop": start + duration,
            }
            result["allure_result_file"] = self.write_allure_result(result)
            artifacts["result_files"].append(result["allure_result_file"])
            case_results.append(result)
            percent = 5 + int(90 * (index + 1) / max(len(cases), 1))
            self.progress(on_progress, percent, f"用例 {name} 执行完成: {status}")

        self.progress(on_progress, 98, "汇总执行结果")
        return self.finalize(case_results, artifacts)


# ---------------------------------------------------------------------------
# Real Playwright runner
# ---------------------------------------------------------------------------
class RealPlaywrightRunner(BaseRunner):
    """Real runner: drives Playwright through ``python -m playwright``/subprocess."""

    name = "real-playwright"
    default_timeout = 300

    def __init__(self, *args, python_executable=None, timeout=None,
                 availability_override=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.python_executable = python_executable or sys.executable
        self.timeout = timeout or getattr(
            settings, "AITS_PLAYWRIGHT_TIMEOUT", self.default_timeout
        )
        #: ``(available, detail)`` injected by tests / callers to skip probing
        self._availability_override = availability_override

    # -- availability ------------------------------------------------------
    def is_available(self) -> tuple[bool, str]:
        """Probe the playwright installation without starting a browser."""
        probe = getattr(self, "_availability_override", None)
        if probe is not None:
            return probe
        try:
            if importlib.util.find_spec("playwright") is None:
                return False, "未安装 playwright 依赖（pip install playwright）"
        except (ImportError, ValueError):  # pragma: no cover - defensive
            return False, "无法检测 playwright 依赖"
        try:
            completed = subprocess.run(
                [self.python_executable, "-m", "playwright", "--version"],
                capture_output=True, text=True, timeout=20, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"无法执行 python -m playwright: {exc}"
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[:200]
            return False, f"python -m playwright 不可用: {detail}"
        return True, (completed.stdout or "").strip()

    # -- execution ---------------------------------------------------------
    def run(self, plan: dict, on_progress=None) -> dict:
        available, detail = self.is_available()
        if not available:
            raise RunnerUnavailable(f"Playwright 不可用: {detail}")

        cases = list(plan.get("cases") or [])
        artifacts = {"allure_results_path": str(self.results_dir()), "result_files": [],
                     "playwright": detail}
        case_results: list[dict] = []
        base = _now_ms()
        with tempfile.TemporaryDirectory(prefix="aits-webui-") as workdir:
            for index, case in enumerate(cases):
                name = case.get("name") or f"case-{index + 1}"
                start = _now_ms()
                status, step_log, error = "passed", [], ""
                script = case.get("script") or ""
                if not script.strip():
                    status, error = "error", "用例缺少可执行脚本，请先生成 Playwright 脚本"
                else:
                    status, error = self._execute_script(index, name, script, workdir)
                duration = max(_now_ms() - start, 1)
                result = {
                    "case_id": case.get("case_id"),
                    "name": name,
                    "status": status,
                    "duration_ms": duration,
                    "steps": step_log,
                    "step_log": step_log,
                    "screenshots": [],
                    "error_message": error,
                    "start": start,
                    "stop": start + duration,
                }
                result["allure_result_file"] = self.write_allure_result(result)
                artifacts["result_files"].append(result["allure_result_file"])
                case_results.append(result)
                self.progress(on_progress, 5 + int(90 * (index + 1) / max(len(cases), 1)),
                              f"用例 {name} 执行完成: {status}")
        return self.finalize(case_results, artifacts)

    def _execute_script(self, index: int, name: str, script: str,
                        workdir: str) -> tuple[str, str]:
        script_path = Path(workdir) / f"case_{index}.py"
        script_path.write_text(script, encoding="utf-8")
        try:
            completed = subprocess.run(
                [self.python_executable, str(script_path)],
                capture_output=True, text=True, timeout=self.timeout, cwd=workdir,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "failed", f"用例超时（>{self.timeout}s）"
        except OSError as exc:
            return "error", f"无法启动 Playwright 子进程: {exc}"
        if completed.returncode == 0:
            return "passed", ""
        tail = (completed.stderr or completed.stdout or "").strip()
        return "failed", _tail(tail)


def _tail(text: str, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[-limit:] if len(text) > limit else text


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------
def execution_mode() -> str:
    return str(getattr(settings, "AITS_EXECUTION_MODE", "simulated") or "simulated").lower()


def get_runner(mode: str | None = None, **kwargs) -> BaseRunner:
    """Return the runner matching ``AITS_EXECUTION_MODE`` (defaults simulated)."""
    mode = (mode or execution_mode()).lower()
    if mode == "real":
        return RealPlaywrightRunner(**kwargs)
    return SimulatedRunner(**kwargs)
