"""Execution engine for API test cases / suites.

Two runners implement the same contract (``docs/ARCHITECTURE.md`` §1.8):

* :class:`SimulatedRunner` - deterministic, never touches the network.  Used by
  tests, demos and CI.  Responses are synthesised from ``mock_response`` when
  provided, otherwise from the assertions themselves so generated positive /
  negative / boundary / security cases behave as expected.
* :class:`HttpRunnerRunner` - real HTTP execution with ``requests``.  Only used
  when ``AITS_EXECUTION_MODE=real``; every failure is captured per case.

Both return::

    {"status": "passed|failed|error",
     "cases": [{"name": ..., "status": ..., "assertions": [...], ...}],
     "summary": {"total": ..., "passed": ..., ...},
     "artifacts": {...}}
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable

from django.conf import settings

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\$\{\s*([^}]+?)\s*\}")
_PATH_TOKEN_RE = re.compile(r"[^\.\[\]]+")

SUPPORTED_ASSERTIONS = {
    "status_code",
    "json_path",
    "equals",
    "eq",
    "contains",
    "len_gte",
    "length_gte",
    "response_time_lt",
    "time_lt",
    "header_present",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def resolve_variables(value: Any, variables: dict | None):
    """Recursively substitute ``${var}`` placeholders."""
    variables = variables or {}
    if isinstance(value, str):
        stripped = value.strip()
        match = _VAR_RE.fullmatch(stripped)
        if match and match.group(1) in variables:
            return variables[match.group(1)]

        def _replace(hit):
            key = hit.group(1)
            return str(variables[key]) if key in variables else hit.group(0)

        return _VAR_RE.sub(_replace, value)
    if isinstance(value, list):
        return [resolve_variables(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: resolve_variables(item, variables) for key, item in value.items()}
    return value


def get_json_path(data: Any, path: str | None, default=None):
    """Read ``a.b[0].c`` style paths from nested dict/list data."""
    if not path:
        return data
    tokens = _PATH_TOKEN_RE.findall(str(path))
    current = data
    for token in tokens:
        if isinstance(current, dict):
            if token in current:
                current = current[token]
                continue
            if token.isdigit() and int(token) in current:
                current = current[int(token)]
                continue
            return default
        if isinstance(current, (list, tuple)):
            try:
                index = int(token)
            except ValueError:
                return default
            if -len(current) <= index < len(current):
                current = current[index]
                continue
            return default
        return default
    return current


def set_json_path(data: dict, path: str | None, value):
    """Write ``value`` into ``data`` following a dotted path (creating nodes)."""
    tokens = _PATH_TOKEN_RE.findall(str(path or ""))
    if not tokens:
        return value
    current = data
    for index, token in enumerate(tokens):
        last = index == len(tokens) - 1
        next_is_index = (not last) and tokens[index + 1].isdigit()
        if isinstance(current, list):
            try:
                position = int(token)
            except ValueError:
                return data
            while len(current) <= position:
                current.append({} if not next_is_index else [])
            if last:
                current[position] = value
            else:
                if not isinstance(current[position], (dict, list)):
                    current[position] = [] if next_is_index else {}
                current = current[position]
            continue
        if not isinstance(current, dict):
            return data
        if last:
            current[token] = value
            continue
        if token not in current or not isinstance(current[token], (dict, list)):
            current[token] = [] if next_is_index else {}
        current = current[token]
    return data


def _loose_equal(actual, expected) -> bool:
    if actual == expected:
        return True
    if actual is None or expected is None:
        return False
    if isinstance(actual, bool) or isinstance(expected, bool):
        return bool(actual) == bool(expected)
    try:
        if isinstance(actual, (int, float)) and isinstance(expected, str):
            return float(actual) == float(expected)
        if isinstance(expected, (int, float)) and isinstance(actual, str):
            return float(expected) == float(actual)
    except (TypeError, ValueError):
        return False
    return str(actual) == str(expected)


def _as_int(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _assertion_expected(assertion: dict):
    return assertion.get(
        "expected", assertion.get("value", assertion.get("expected_value"))
    )


def _assertion_path(assertion: dict) -> str:
    return (
        assertion.get("path")
        or assertion.get("field")
        or assertion.get("json_path")
        or ""
    )


def evaluate_assertion(assertion: dict, response: dict) -> dict:
    """Evaluate one assertion against a normalised response dict."""
    if not isinstance(assertion, dict):
        return {"type": "unknown", "status": "skipped", "passed": True,
                "message": "非法断言，已跳过"}
    kind = str(assertion.get("type") or "").lower()
    expected = _assertion_expected(assertion)
    path = _assertion_path(assertion)
    json_body = response.get("json", response.get("body_json"))
    if json_body is None:
        json_body = {}

    if kind not in SUPPORTED_ASSERTIONS:
        return {
            "type": kind or "unknown",
            "path": path,
            "expected": expected,
            "actual": None,
            "status": "skipped",
            "passed": True,
            "message": f"不支持的断言类型 {kind or '(空)'}，已跳过",
        }

    try:
        if kind == "status_code":
            actual = _as_int(response.get("status_code", 0))
            passed = actual == _as_int(expected, -1)
            target = "status_code"
        elif kind in ("json_path", "equals", "eq"):
            actual = get_json_path(json_body, path)
            passed = _loose_equal(actual, expected)
            target = path or "content"
        elif kind == "contains":
            if path:
                actual = get_json_path(json_body, path)
            else:
                actual = json_body
            if isinstance(actual, str):
                passed = str(expected) in actual
            elif isinstance(actual, dict):
                if isinstance(expected, dict):
                    passed = all(_loose_equal(actual.get(key), value)
                                 for key, value in expected.items())
                elif isinstance(expected, (list, tuple)):
                    passed = all(item in actual for item in expected)
                else:
                    passed = expected in actual or str(expected) in json.dumps(
                        actual, ensure_ascii=False
                    )
            elif isinstance(actual, (list, tuple)):
                if isinstance(expected, (list, tuple)):
                    passed = all(item in actual for item in expected)
                else:
                    passed = expected in actual
            else:
                passed = _loose_equal(actual, expected)
            target = path or "body"
        elif kind in ("len_gte", "length_gte"):
            actual = get_json_path(json_body, path) if path else json_body
            try:
                passed = len(actual) >= _as_int(expected, 0)
            except TypeError:
                passed = False
            target = path or "content"
        elif kind in ("response_time_lt", "time_lt"):
            actual = _as_int(response.get("time_ms", response.get("duration_ms", 0)))
            passed = actual < _as_int(expected, 0)
            target = "response_time_ms"
        else:  # header_present
            headers = response.get("headers") or {}
            actual = expected if expected in headers else None
            passed = expected in headers
            target = "headers"

        message = "断言通过" if passed else f"断言失败: 期望 {expected!r}，实际 {actual!r}"
        return {
            "type": kind,
            "path": path,
            "expected": expected,
            "actual": actual,
            "status": "passed" if passed else "failed",
            "passed": bool(passed),
            "message": message,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "type": kind,
            "path": path,
            "expected": expected,
            "actual": None,
            "status": "failed",
            "passed": False,
            "message": f"断言执行异常: {exc}",
        }


def evaluate_assertions(assertions, response: dict) -> list[dict]:
    return [evaluate_assertion(assertion, response) for assertion in (assertions or [])]


def _text_body(json_body) -> str:
    if isinstance(json_body, str):
        return json_body
    try:
        return json.dumps(json_body, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(json_body)


def synthesize_response(request_config: dict, assertions) -> dict:
    """Deterministically produce a response for the simulated runner."""
    config = request_config or {}
    mock = config.get("mock_response") or config.get("response")
    if isinstance(mock, dict) and mock:
        body = mock.get("json", mock.get("body", {}))
        if isinstance(body, str):
            parsed = None
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                pass
            body_value = parsed if parsed is not None else body
        else:
            body_value = body
        return {
            "status_code": _as_int(mock.get("status_code", 200), 200),
            "json": body_value,
            "body": body if isinstance(body, str) else _text_body(body_value),
            "headers": mock.get("headers") or {"Content-Type": "application/json"},
            "time_ms": _as_int(mock.get("time_ms", mock.get("response_time_ms", 100)), 100),
        }

    status_code = 200
    json_body: Any = {}
    headers = {"Content-Type": "application/json"}
    time_ms = 100

    for assertion in assertions or []:
        if not isinstance(assertion, dict):
            continue
        kind = str(assertion.get("type") or "").lower()
        expected = _assertion_expected(assertion)
        path = _assertion_path(assertion)
        if kind == "status_code":
            status_code = _as_int(expected, 200)
        elif kind in ("json_path", "equals", "eq"):
            if path:
                if not isinstance(json_body, dict):
                    json_body = {}
                set_json_path(json_body, path, expected)
            else:
                json_body = expected
        elif kind == "contains":
            if path:
                if not isinstance(json_body, dict):
                    json_body = {}
                set_json_path(json_body, path, expected)
            elif isinstance(expected, dict):
                json_body = expected
            else:
                json_body = {"message": expected}
        elif kind in ("len_gte", "length_gte"):
            length = max(0, min(_as_int(expected, 0), 1000))
            items = ["item"] * length
            if path:
                if not isinstance(json_body, dict):
                    json_body = {}
                set_json_path(json_body, path, items)
            else:
                json_body = items
        elif kind in ("response_time_lt", "time_lt"):
            time_ms = max(1, _as_int(expected, 100) - 1)
        elif kind == "header_present":
            headers[str(expected)] = "present"

    return {
        "status_code": status_code,
        "json": json_body,
        "body": _text_body(json_body),
        "headers": headers,
        "time_ms": time_ms,
    }


def build_request_preview(request_config: dict, variables: dict | None = None) -> dict:
    config = resolve_variables(dict(request_config or {}), variables)
    config.pop("mock_response", None)
    config.pop("response", None)
    preview = {
        "method": str(config.get("method") or "GET").upper(),
        "url": config.get("url") or config.get("path") or "/",
        "params": config.get("params") or config.get("parameters") or {},
        "headers": config.get("headers") or {},
    }
    body = config.get("body")
    if isinstance(body, dict) and body:
        preview["body"] = body
    elif config.get("json") is not None:
        preview["body"] = config.get("json")
    elif config.get("data") is not None:
        preview["body"] = config.get("data")
    return preview


# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------
class BaseRunner:
    """Contract every API test runner implements."""

    mode = "base"

    def run(self, plan: dict, on_progress: Callable[[int, str], None] | None = None) -> dict:
        plan = plan or {}
        cases = plan.get("cases") or []
        variables = dict(plan.get("variables") or {})
        total = len(cases)
        started = time.perf_counter()
        results: list[dict] = []

        if on_progress:
            try:
                on_progress(0, f"开始执行 {total} 个用例")
            except Exception:  # pragma: no cover - callback must never break runs
                logger.debug("on_progress callback failed", exc_info=True)

        for index, case in enumerate(cases):
            result = self._run_case(case, variables)
            results.append(result)
            variables.update(result.get("variables") or {})
            if on_progress:
                progress = int((index + 1) / total * 100) if total else 100
                try:
                    on_progress(progress, f"{result.get('name')} {result.get('status')}")
                except Exception:  # pragma: no cover
                    logger.debug("on_progress callback failed", exc_info=True)

        passed = sum(1 for item in results if item.get("status") == "passed")
        failed = sum(1 for item in results if item.get("status") == "failed")
        skipped = sum(1 for item in results if item.get("status") == "skipped")
        errors = sum(1 for item in results if item.get("status") == "error")
        executed = total - skipped
        pass_rate = round(passed / executed * 100, 2) if executed else 0.0
        duration_ms = int((time.perf_counter() - started) * 1000)

        if errors:
            status = "error"
        elif failed:
            status = "failed"
        else:
            status = "passed"

        return {
            "status": status,
            "cases": results,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
                "pass_rate": pass_rate,
                "duration_ms": duration_ms,
                "mode": self.mode,
            },
            "artifacts": {"mode": self.mode},
        }

    # -- internals ---------------------------------------------------------
    def _run_case(self, case: dict, variables: dict) -> dict:
        case = case or {}
        if case.get("skip"):
            return {
                "id": case.get("id"),
                "name": case.get("name") or "未命名用例",
                "status": "skipped",
                "duration_ms": 0,
                "request": {},
                "response": {},
                "assertions": [],
                "variables": {},
                "error_message": "",
                "step_log": [],
            }
        request_config = case.get("request_config") or {}
        case_type = case.get("case_type") or "endpoint"
        steps = request_config.get("steps") if isinstance(request_config, dict) else None
        if case_type == "scenario" and isinstance(steps, list) and steps:
            return self._run_scenario(case, steps, variables)
        return self._run_endpoint(case, request_config, variables)

    def _run_endpoint(self, case: dict, request_config: dict, variables: dict) -> dict:
        name = case.get("name") or "未命名用例"
        assertions = case.get("assertions") or []
        extract = case.get("extract") or {}
        started = time.perf_counter()
        try:
            response = self._perform_request(request_config, assertions, variables)
            assertion_results = evaluate_assertions(assertions, response)
            failed = [item for item in assertion_results if item.get("status") == "failed"]
            status = "failed" if failed else "passed"
            error_message = "；".join(item["message"] for item in failed)
            extracted = self._extract_values(extract, response, variables)
            duration_ms = _as_int(response.get("time_ms"), 0) or int(
                (time.perf_counter() - started) * 1000
            )
            return {
                "id": case.get("id"),
                "test_case_id": case.get("test_case_id") or case.get("id"),
                "name": name,
                "status": status,
                "duration_ms": duration_ms,
                "request": build_request_preview(request_config, variables),
                "response": self._response_payload(response),
                "assertions": assertion_results,
                "variables": extracted,
                "error_message": error_message,
                "step_log": [
                    {
                        "step": name,
                        "status": status,
                        "duration_ms": duration_ms,
                        "assertions": assertion_results,
                    }
                ],
            }
        except Exception as exc:
            logger.exception("case execution failed: %s", exc)
            return {
                "id": case.get("id"),
                "test_case_id": case.get("test_case_id") or case.get("id"),
                "name": name,
                "status": "error",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "request": build_request_preview(request_config, variables),
                "response": {},
                "assertions": [],
                "variables": {},
                "error_message": str(exc),
                "step_log": [{"step": name, "status": "error", "error": str(exc)}],
            }

    def _run_scenario(self, case: dict, steps: list, variables: dict) -> dict:
        name = case.get("name") or "未命名场景"
        started = time.perf_counter()
        step_log: list[dict] = []
        requests: list[dict] = []
        responses: list[dict] = []
        all_assertions: list[dict] = []
        extracted: dict = {}
        status = "passed"
        error_message = ""
        duration_ms = 0
        try:
            for index, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                step_name = step.get("name") or f"步骤{index + 1}"
                step_config = step.get("request_config") or step.get("request") or step
                step_assertions = step.get("assertions", case.get("assertions") or [])
                step_extract = step.get("extract", case.get("extract") or {})
                response = self._perform_request(step_config, step_assertions, variables)
                step_results = evaluate_assertions(step_assertions, response)
                for item in step_results:
                    item["step"] = step_name
                all_assertions.extend(step_results)
                step_failed = [item for item in step_results if item.get("status") == "failed"]
                if step_failed and status == "passed":
                    status = "failed"
                    error_message = "；".join(item["message"] for item in step_failed)
                extracted.update(self._extract_values(step_extract, response, variables))
                duration_ms += _as_int(response.get("time_ms"), 0)
                requests.append({"name": step_name, **build_request_preview(step_config, variables)})
                responses.append({"name": step_name, **self._response_payload(response)})
                step_log.append(
                    {
                        "step": step_name,
                        "status": "failed" if step_failed else "passed",
                        "duration_ms": _as_int(response.get("time_ms"), 0),
                        "assertions": step_results,
                    }
                )
            if not duration_ms:
                duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "id": case.get("id"),
                "test_case_id": case.get("test_case_id") or case.get("id"),
                "name": name,
                "status": status,
                "duration_ms": duration_ms,
                "request": {"steps": requests},
                "response": {"steps": responses},
                "assertions": all_assertions,
                "variables": extracted,
                "error_message": error_message,
                "step_log": step_log,
            }
        except Exception as exc:
            logger.exception("scenario execution failed: %s", exc)
            return {
                "id": case.get("id"),
                "test_case_id": case.get("test_case_id") or case.get("id"),
                "name": name,
                "status": "error",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "request": {"steps": requests},
                "response": {"steps": responses},
                "assertions": all_assertions,
                "variables": extracted,
                "error_message": str(exc),
                "step_log": step_log + [{"step": name, "status": "error", "error": str(exc)}],
            }

    @staticmethod
    def _extract_values(extract, response: dict, variables: dict) -> dict:
        extracted: dict = {}
        if not isinstance(extract, dict):
            return extracted
        json_body = response.get("json", {})
        for key, path in extract.items():
            if isinstance(path, dict):
                path = path.get("path")
            value = get_json_path(json_body, str(path or ""))
            if value is None:
                continue
            extracted[str(key)] = value
            variables[str(key)] = value
        return extracted

    @staticmethod
    def _response_payload(response: dict) -> dict:
        return {
            "status_code": response.get("status_code"),
            "headers": response.get("headers") or {},
            "json": response.get("json"),
            "body": response.get("body"),
            "time_ms": response.get("time_ms"),
        }

    def _perform_request(self, request_config: dict, assertions, variables: dict) -> dict:
        raise NotImplementedError


class SimulatedRunner(BaseRunner):
    """Deterministic in-process runner - no sockets, no external services."""

    mode = "simulated"

    def _perform_request(self, request_config: dict, assertions, variables: dict) -> dict:
        config = resolve_variables(dict(request_config or {}), variables)
        return synthesize_response(config, assertions)


class HttpRunnerRunner(BaseRunner):
    """Real HTTP runner based on ``requests`` (settings.AITS_EXECUTION_MODE=real)."""

    mode = "real"

    def _perform_request(self, request_config: dict, assertions, variables: dict) -> dict:
        import requests

        config = resolve_variables(dict(request_config or {}), variables)
        method = str(config.get("method") or "GET").upper()
        url = str(config.get("url") or config.get("path") or "/")
        if not url.lower().startswith(("http://", "https://")):
            base_url = str(config.get("base_url") or "").rstrip("/")
            url = f"{base_url}{url}" if base_url else url
        headers = dict(config.get("headers") or {})
        params = config.get("params") or config.get("parameters") or None
        body = config.get("body")
        timeout = config.get("timeout") or 30
        kwargs: dict = {"headers": headers, "params": params, "timeout": timeout}
        if isinstance(body, dict) and body:
            mode = body.get("mode")
            if mode in ("urlencoded", "formdata"):
                kwargs["data"] = body.get(mode) or {}
            elif mode == "graphql":
                kwargs["json"] = body.get("graphql") or {}
            else:
                payload = body.get("json", body.get("raw"))
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        pass
                kwargs["json"] = payload
        elif config.get("json") is not None:
            kwargs["json"] = config.get("json")
        elif config.get("data") is not None:
            kwargs["data"] = config.get("data")

        response = requests.request(method, url, **kwargs)
        try:
            parsed_body = response.json()
        except ValueError:
            parsed_body = None
        return {
            "status_code": response.status_code,
            "json": parsed_body if parsed_body is not None else {},
            "body": response.text,
            "headers": dict(response.headers),
            "time_ms": int(response.elapsed.total_seconds() * 1000),
        }


def get_runner(mode: str | None = None) -> BaseRunner:
    """Factory honouring ``settings.AITS_EXECUTION_MODE``."""
    resolved = (mode or getattr(settings, "AITS_EXECUTION_MODE", "simulated") or "").lower()
    if resolved == "real":
        return HttpRunnerRunner()
    return SimulatedRunner()
