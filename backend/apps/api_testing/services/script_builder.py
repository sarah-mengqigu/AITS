"""HttpRunner (v3/v4) YAML generation from AITS test cases.

Pure functions: the only external dependency is PyYAML.  The produced document
contains ``config`` (name/base_url/variables/verify/stage) and one or more
``teststeps`` (request/validate/extract).
"""

from __future__ import annotations

from typing import Any

import yaml

from apps.common.api.api_exception_handler import BusinessError

__all__ = ["build_httprunner_yaml", "build_case_from_endpoint", "assertion_to_validate"]


def _get(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _normalise_path(path: str) -> str:
    return str(path or "").strip().strip("/")


def _jmespath_for(path: str | None, default: str = "content") -> str:
    cleaned = _normalise_path(path) if path else ""
    if not cleaned:
        return default
    if cleaned.startswith(("content", "body", "headers", "status_code", "response_time_ms")):
        return cleaned
    return f"content.{cleaned}"


def assertion_to_validate(assertion: dict) -> dict | None:
    """Translate one AITS assertion into an HttpRunner ``validate`` entry."""
    if not isinstance(assertion, dict):
        return None
    kind = str(assertion.get("type") or "").lower()
    expected = assertion.get("expected", assertion.get("value", assertion.get("expected_value")))
    path = assertion.get("path") or assertion.get("field") or assertion.get("json_path") or ""
    if kind == "status_code":
        return {"eq": ["status_code", expected]}
    if kind in ("json_path", "equals", "eq"):
        return {"eq": [_jmespath_for(path), expected]}
    if kind == "contains":
        return {"contains": [_jmespath_for(path, "body"), expected]}
    if kind in ("len_gte", "length_gte"):
        return {"len_gte": [_jmespath_for(path), expected]}
    if kind in ("response_time_lt", "time_lt"):
        return {"lt": ["response_time_ms", expected]}
    if kind == "header_present":
        return {"contains": ["headers", expected]}
    return None


def _extract_expr(path: str) -> str:
    cleaned = _normalise_path(path)
    if not cleaned:
        return "content"
    if cleaned.startswith(("content", "body", "headers")):
        return cleaned
    return f"content.{cleaned}"


def _request_from_config(config: dict) -> dict:
    """Build the ``request`` block of one teststep."""
    request: dict = {}
    method = str(config.get("method") or "GET").upper()
    url = config.get("url") or config.get("path") or "/"
    request["method"] = method
    request["url"] = str(url)

    headers = config.get("headers")
    if isinstance(headers, dict) and headers:
        request["headers"] = dict(headers)

    params = config.get("params") or config.get("parameters")
    if isinstance(params, dict) and params:
        request["params"] = dict(params)

    body = config.get("body")
    if isinstance(body, dict) and body:
        mode = body.get("mode")
        if mode == "raw" or "json" in body:
            payload = body.get("json", body.get("raw"))
            if isinstance(payload, str):
                try:
                    payload = yaml.safe_load(payload)
                except yaml.YAMLError:
                    pass
            request["json"] = payload
        elif mode == "urlencoded" or "urlencoded" in body:
            request["data"] = body.get("urlencoded") or {}
        elif mode == "formdata" or "formdata" in body:
            request["data"] = body.get("formdata") or {}
        elif mode == "graphql" or "graphql" in body:
            request["json"] = body.get("graphql") or {}
        else:
            request["json"] = body
    elif "json" in config and config.get("json") is not None:
        request["json"] = config["json"]
    elif "data" in config and config.get("data") is not None:
        request["data"] = config["data"]

    timeout = config.get("timeout")
    if timeout:
        request["timeout"] = timeout
    return request


def _validate_list(assertions) -> list[dict]:
    result: list[dict] = []
    for assertion in assertions or []:
        converted = assertion_to_validate(assertion)
        if converted:
            result.append(converted)
    return result


def _extract_block(extract) -> dict:
    if not isinstance(extract, dict):
        return {}
    return {str(key): _extract_expr(str(path)) for key, path in extract.items() if path}


def _build_step(name: str, config: dict, assertions, extract) -> dict:
    step: dict = {"name": name or "step"}
    step["request"] = _request_from_config(config)
    validates = _validate_list(assertions)
    if validates:
        step["validate"] = validates
    extract_block = _extract_block(extract)
    if extract_block:
        step["extract"] = extract_block
    return step


def build_httprunner_yaml(case) -> str:
    """Render a test case (model instance or dict) as HttpRunner YAML text."""
    if case is None:
        raise BusinessError(message="用例不存在", code="not_found", status_code=404)
    name = str(_get(case, "name", "") or "未命名用例")
    request_config = _get(case, "request_config", {}) or {}
    if not isinstance(request_config, dict):
        request_config = {}
    assertions = _get(case, "assertions", []) or []
    extract = _get(case, "extract", {}) or {}
    case_type = _get(case, "case_type", "endpoint")

    config_variables = request_config.get("variables")
    variables = dict(config_variables) if isinstance(config_variables, dict) else {}
    base_url = request_config.get("base_url") or request_config.get("host") or ""
    verify = request_config.get("verify", False)
    stage = request_config.get("stage") or {"enabled": False}

    scenario_steps = request_config.get("steps")
    if case_type == "scenario" and isinstance(scenario_steps, list) and scenario_steps:
        steps = []
        for index, raw_step in enumerate(scenario_steps):
            if not isinstance(raw_step, dict):
                continue
            step_name = raw_step.get("name") or f"{name} - 步骤{index + 1}"
            step_config = raw_step.get("request_config") or raw_step.get("request") or raw_step
            step_assertions = raw_step.get("assertions", assertions)
            step_extract = raw_step.get("extract", extract)
            steps.append(_build_step(step_name, step_config, step_assertions, step_extract))
        if not steps:
            steps = [_build_step(name, request_config, assertions, extract)]
    else:
        steps = [_build_step(name, request_config, assertions, extract)]

    document = {
        "config": {
            "name": name,
            "base_url": str(base_url or ""),
            "variables": variables,
            "verify": bool(verify),
            "stage": stage,
        },
        "teststeps": steps,
    }
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False,
                          default_flow_style=False)


def build_case_from_endpoint(endpoint) -> dict:
    """Turn an :class:`APIEndpoint` into a test case payload dict."""
    if endpoint is None:
        raise BusinessError(message="端点不存在", code="not_found", status_code=404)

    parameters = _get(endpoint, "parameters", []) or []
    query: dict = {}
    path_values: dict = {}
    header_params: dict = {}
    for param in parameters:
        if not isinstance(param, dict):
            continue
        where = param.get("in")
        key = param.get("name")
        if not key:
            continue
        value = param.get("example")
        if value is None:
            value = ""
        if where == "query":
            query[key] = value
        elif where == "path":
            path_values[key] = value
        elif where == "header":
            header_params[key] = value

    path = str(_get(endpoint, "path", "/") or "/")
    for key, value in path_values.items():
        path = path.replace("{" + str(key) + "}", str(value))

    headers = dict(_get(endpoint, "headers", {}) or {})
    headers.update(header_params)

    request_body = _get(endpoint, "request_body", {}) or {}
    body = {}
    if isinstance(request_body, dict) and request_body:
        example = request_body.get("example")
        content_type = request_body.get("content_type") or ""
        if "json" in (content_type or ""):
            body = {"mode": "raw", "json": example}
        elif "form" in (content_type or ""):
            body = {"mode": "urlencoded", "urlencoded": example or {}}
        elif example is not None:
            body = {"mode": "raw", "raw": example}

    responses = _get(endpoint, "responses", {}) or {}
    expected_status = 200
    if isinstance(responses, dict):
        for code in sorted(responses.keys(), key=lambda item: str(item)):
            try:
                numeric = int(code)
            except (TypeError, ValueError):
                continue
            if 200 <= numeric < 300:
                expected_status = numeric
                break

    assertions = [{"type": "status_code", "expected": expected_status}]
    method = str(_get(endpoint, "method", "get") or "get").upper()
    if method in ("GET", "HEAD", "DELETE"):
        request_config = {"method": method, "url": path, "params": query,
                          "headers": headers}
    else:
        request_config = {"method": method, "url": path, "params": query,
                          "headers": headers, "body": body}

    display = _get(endpoint, "summary", "") or _get(endpoint, "operation_id", "")
    name = display or f"{method} {path}"
    return {
        "name": name,
        "case_type": "endpoint",
        "test_type": "positive",
        "description": _get(endpoint, "description", "") or "",
        "request_config": request_config,
        "assertions": assertions,
        "extract": {},
        "source": "manual",
        "priority": 2,
    }
