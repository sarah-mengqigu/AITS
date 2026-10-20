"""AI / rule based generation of API test cases.

The AI dependency is **optional and lazy**: ``ai_core`` may not be installed yet or
may fail at runtime, in which case the deterministic rule generator is used.  No
test may fail because of a missing LLM.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from apps.common.api.api_exception_handler import BusinessError
from apps.common.parsers.yaml_json import extract_first_object

logger = logging.getLogger(__name__)

CASE_TYPES = {"endpoint", "scenario"}
TEST_TYPES = {"positive", "negative", "boundary", "security", "performance"}
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


# ---------------------------------------------------------------------------
# helpers (model instance or dict)
# ---------------------------------------------------------------------------
def _get(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _display_name(endpoint) -> str:
    summary = _get(endpoint, "summary", "") or _get(endpoint, "operation_id", "")
    method = str(_get(endpoint, "method", "get") or "get").upper()
    path = _get(endpoint, "path", "/") or "/"
    return summary or f"{method} {path}"


def _response_codes(endpoint) -> list[str]:
    responses = _get(endpoint, "responses", {}) or {}
    if not isinstance(responses, dict):
        return []
    return [str(code) for code in responses.keys()]


def _pick_code(codes: list[str], predicate, default: int | None) -> int | None:
    numeric = []
    for code in codes:
        try:
            numeric.append(int(str(code)))
        except (TypeError, ValueError):
            continue
    for value in sorted(numeric):
        if predicate(value):
            return value
    return default


def _path_with_values(endpoint) -> str:
    path = str(_get(endpoint, "path", "/") or "/")
    for param in _get(endpoint, "parameters", []) or []:
        if not isinstance(param, dict) or param.get("in") != "path":
            continue
        name = param.get("name")
        if not name:
            continue
        value = param.get("example")
        if value is None:
            value = "1"
        path = path.replace("{" + str(name) + "}", str(value))
    return _PLACEHOLDER_RE.sub("1", path)


def _query_params(endpoint) -> dict:
    params = {}
    for param in _get(endpoint, "parameters", []) or []:
        if not isinstance(param, dict) or param.get("in") != "query":
            continue
        name = param.get("name")
        if not name:
            continue
        value = param.get("example")
        params[str(name)] = "" if value is None else value
    return params


def _headers(endpoint) -> dict:
    headers = _get(endpoint, "headers", {}) or {}
    return dict(headers) if isinstance(headers, dict) else {}


def _body_block(endpoint) -> dict:
    request_body = _get(endpoint, "request_body", {}) or {}
    if not isinstance(request_body, dict) or not request_body:
        return {}
    content_type = str(request_body.get("content_type") or "")
    example = request_body.get("example")
    if example is None:
        return {}
    if "json" in content_type or isinstance(example, (dict, list)):
        return {"mode": "raw", "json": example}
    if "form" in content_type:
        return {"mode": "urlencoded", "urlencoded": example if isinstance(example, dict) else {}}
    return {"mode": "raw", "raw": example}


def _base_request_config(endpoint) -> dict:
    method = str(_get(endpoint, "method", "get") or "get").upper()
    config = {
        "method": method,
        "url": _path_with_values(endpoint),
        "params": _query_params(endpoint),
        "headers": _headers(endpoint),
    }
    body = _body_block(endpoint)
    if body:
        config["body"] = body
    return config


def _copy_config(config: dict) -> dict:
    copied = {
        "method": config.get("method"),
        "url": config.get("url"),
        "params": dict(config.get("params") or {}),
        "headers": dict(config.get("headers") or {}),
    }
    if isinstance(config.get("body"), dict):
        body = dict(config["body"])
        if isinstance(body.get("json"), dict):
            body["json"] = dict(body["json"])
        copied["body"] = body
    return copied


def _rule_cases(endpoint) -> list[dict]:
    codes = _response_codes(endpoint)
    success = _pick_code(codes, lambda code: 200 <= code < 300, 200)
    client_error = _pick_code(codes, lambda code: 400 <= code < 500, 400)
    unauthorized = _pick_code(codes, lambda code: code in (401, 403), 401)
    base_config = _base_request_config(endpoint)
    display = _display_name(endpoint)
    description = str(_get(endpoint, "description", "") or "")

    # -- positive ----------------------------------------------------------
    positive_config = _copy_config(base_config)
    positive = {
        "name": f"{display} - 正向请求",
        "case_type": "endpoint",
        "test_type": "positive",
        "description": description or "使用规范示例值验证正常调用",
        "request_config": positive_config,
        "assertions": [
            {"type": "status_code", "expected": success},
            {"type": "response_time_lt", "expected": 3000},
        ],
        "extract": {},
        "source": "ai",
        "priority": 1,
    }

    # -- negative ----------------------------------------------------------
    negative_config = _copy_config(base_config)
    negative_reason = "缺少必填参数"
    body_json = (negative_config.get("body") or {}).get("json")
    if isinstance(body_json, dict) and body_json:
        first_key = next(iter(body_json))
        body_json.pop(first_key, None)
        negative_config["body"]["json"] = body_json
        negative_reason = f"缺少必填字段 {first_key}"
    else:
        required_query = [
            param.get("name")
            for param in _get(endpoint, "parameters", []) or []
            if isinstance(param, dict) and param.get("in") == "query" and param.get("required")
        ]
        if required_query:
            negative_config["params"].pop(required_query[0], None)
            negative_reason = f"缺少必填参数 {required_query[0]}"
        elif negative_config.get("params"):
            first_key = next(iter(negative_config["params"]))
            negative_config["params"][first_key] = "__invalid__"
            negative_reason = f"参数 {first_key} 类型非法"
        else:
            negative_config.setdefault("params", {})["__invalid_field__"] = "x"
    negative = {
        "name": f"{display} - 反向校验",
        "case_type": "endpoint",
        "test_type": "negative",
        "description": negative_reason,
        "request_config": negative_config,
        "assertions": [{"type": "status_code", "expected": client_error or 400}],
        "extract": {},
        "source": "ai",
        "priority": 2,
    }

    # -- boundary ----------------------------------------------------------
    boundary_config = _copy_config(base_config)
    boundary_reason = "超长字符串参数"
    boundary_json = (boundary_config.get("body") or {}).get("json")
    if isinstance(boundary_json, dict) and boundary_json:
        string_key = next(
            (key for key, value in boundary_json.items() if isinstance(value, str)), None
        )
        if string_key:
            boundary_json[string_key] = "a" * 1024
            boundary_reason = f"字段 {string_key} 超长（1024 字符）"
        else:
            number_key = next(
                (key for key, value in boundary_json.items()
                 if isinstance(value, (int, float)) and not isinstance(value, bool)),
                None,
            )
            if number_key:
                boundary_json[number_key] = -1
                boundary_reason = f"字段 {number_key} 使用负数边界值"
            else:
                first_key = next(iter(boundary_json))
                boundary_json[first_key] = []
                boundary_reason = f"字段 {first_key} 使用空数组边界值"
        boundary_config["body"]["json"] = boundary_json
    else:
        boundary_config.setdefault("params", {})["_boundary"] = "a" * 1024
    boundary = {
        "name": f"{display} - 边界值校验",
        "case_type": "endpoint",
        "test_type": "boundary",
        "description": boundary_reason,
        "request_config": boundary_config,
        "assertions": [{"type": "status_code", "expected": client_error or 400}],
        "extract": {},
        "source": "ai",
        "priority": 3,
    }

    # -- security ----------------------------------------------------------
    security_config = _copy_config(base_config)
    security_headers = security_config.get("headers") or {}
    security_headers.pop("Authorization", None)
    security_headers.pop("authorization", None)
    security_config["headers"] = security_headers
    injection = "' OR '1'='1"
    security_json = (security_config.get("body") or {}).get("json")
    if isinstance(security_json, dict) and security_json:
        first_key = next(iter(security_json))
        security_json[first_key] = injection
        security_config["body"]["json"] = security_json
    elif security_config.get("params"):
        first_key = next(iter(security_config["params"]))
        security_config["params"][first_key] = injection
    else:
        security_config.setdefault("params", {})["q"] = injection
    security = {
        "name": f"{display} - 安全未授权/注入校验",
        "case_type": "endpoint",
        "test_type": "security",
        "description": "移除鉴权头并注入 SQL 片段，期望服务端拒绝",
        "request_config": security_config,
        "assertions": [{"type": "status_code", "expected": unauthorized or 401}],
        "extract": {},
        "source": "ai",
        "priority": 4,
    }

    return [positive, negative, boundary, security]


# ---------------------------------------------------------------------------
# LLM plumbing
# ---------------------------------------------------------------------------
def _llm_text(llm_service, messages) -> str:
    result = llm_service.chat(messages)
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "content", "response", "message"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return str(result)
    for attr in ("text", "content", "response"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return str(result)


def _normalise_case(raw, endpoint) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    request_config = raw.get("request_config")
    if not isinstance(request_config, dict) or not request_config:
        request = raw.get("request")
        if isinstance(request, dict):
            request_config = {
                "method": request.get("method") or _get(endpoint, "method", "get"),
                "url": request.get("url") or _get(endpoint, "path", "/"),
                "params": request.get("params") or {},
                "headers": request.get("headers") or {},
            }
            if request.get("body") is not None:
                request_config["body"] = request["body"]
        else:
            request_config = _base_request_config(endpoint)
    assertions = raw.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        assertions = [{"type": "status_code", "expected": 200}]
    assertions = [item for item in assertions if isinstance(item, dict)]
    test_type = raw.get("test_type")
    if test_type not in TEST_TYPES:
        test_type = "positive"
    case_type = raw.get("case_type")
    if case_type not in CASE_TYPES:
        case_type = "endpoint"
    priority = raw.get("priority", 2)
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        priority = 2
    extract = raw.get("extract")
    if not isinstance(extract, dict):
        extract = {}
    return {
        "name": name,
        "case_type": case_type,
        "test_type": test_type,
        "description": str(raw.get("description") or ""),
        "request_config": request_config,
        "assertions": assertions,
        "extract": extract,
        "source": "ai",
        "priority": priority,
    }


def _llm_cases(endpoint, llm_service) -> list[dict]:
    display = _display_name(endpoint)
    payload = {
        "name": display,
        "method": str(_get(endpoint, "method", "get") or "get").upper(),
        "path": _get(endpoint, "path", "/"),
        "parameters": _get(endpoint, "parameters", []) or [],
        "request_body": _get(endpoint, "request_body", {}) or {},
        "responses": _get(endpoint, "responses", {}) or {},
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是 API 测试专家。请输出严格 JSON，不要输出解释。"
                '格式：{"cases":[{"name":"","test_type":"positive|negative|boundary|security",'
                '"description":"","request_config":{"method":"GET","url":"/path",'
                '"params":{},"headers":{},"body":null},"assertions":[{"type":"status_code",'
                '"expected":200}],"extract":{},"priority":1}]}'
            ),
        },
        {
            "role": "user",
            "content": (
                "为下面接口生成正向、反向、边界、安全四类测试用例，"
                f"接口信息：{payload}"
            ),
        },
    ]
    text = _llm_text(llm_service, messages)
    parsed = extract_first_object(text)
    raw_cases = None
    if isinstance(parsed, dict):
        raw_cases = parsed.get("cases")
    elif isinstance(parsed, list):
        raw_cases = parsed
    if not isinstance(raw_cases, list):
        return []
    normalised = [_normalise_case(item, endpoint) for item in raw_cases]
    return [item for item in normalised if item]


def _try_llm_service(llm_service):
    """Lazily build an ``LLMService`` when the caller did not supply one."""
    if llm_service is not None:
        return llm_service
    try:
        from apps.ai_core.services.llm_service import LLMService

        return LLMService()
    except Exception:  # ImportError / DB errors / missing app
        logger.info("ai_core unavailable, falling back to rule based generation")
        return None


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def generate_endpoint_cases(endpoint, llm_service=None, use_ai: bool = False) -> list[dict]:
    """Generate positive / negative / boundary / security cases for an endpoint.

    ``llm_service`` is explicit: when omitted the deterministic rule generator is
    used.  Callers that want the AI path (and accept degradation) pass
    ``use_ai=True`` - the optional ``ai_core`` dependency is imported lazily and
    any failure falls back to the rules.
    """
    if endpoint is None:
        raise BusinessError(message="端点不存在", code="not_found", status_code=404)

    service = llm_service
    if service is None and use_ai:
        service = _try_llm_service(None)
    if service is not None:
        try:
            generated = _llm_cases(endpoint, service)
            if generated:
                return generated
            logger.info("LLM returned no usable cases, falling back to rules")
        except Exception as exc:  # noqa: BLE001 - degrade, never fail
            logger.warning("LLM case generation failed: %s", exc)

    return _rule_cases(endpoint)


def _scenario_case(name: str, description: str, steps: list[dict]) -> dict:
    return {
        "name": name,
        "case_type": "scenario",
        "test_type": "positive",
        "description": description,
        "request_config": {"steps": steps},
        "assertions": [],
        "extract": {},
        "source": "ai",
        "priority": 2,
    }


def _rule_scenario(natural_language: str, project) -> dict:
    text = str(natural_language or "").strip()
    first_line = text.splitlines()[0].strip() if text else ""
    name = first_line[:80] or "AI 生成测试场景"
    lowered = text.lower()

    steps: list[dict] = []
    try:
        endpoints = list(
            project.api_endpoints.filter(is_active=True).order_by("path", "method")[:200]
        )
    except Exception:  # pragma: no cover - defensive
        endpoints = []

    matched = []
    for endpoint in endpoints:
        path = str(endpoint.path or "")
        tokens = [token for token in re.split(r"[/{}_-]+", path.lower()) if len(token) > 2]
        if path and (path.lower() in lowered or any(token in lowered for token in tokens)):
            matched.append(endpoint)
        if len(matched) >= 5:
            break

    for endpoint in matched:
        config = _base_request_config(endpoint)
        success = _pick_code(_response_codes(endpoint),
                             lambda code: 200 <= code < 300, 200)
        steps.append(
            {
                "name": _display_name(endpoint),
                "request_config": config,
                "assertions": [{"type": "status_code", "expected": success}],
                "extract": {},
            }
        )

    if not steps:
        steps.append(
            {
                "name": "健康检查",
                "request_config": {
                    "method": "GET",
                    "url": "/",
                    "params": {},
                    "headers": {"Accept": "application/json"},
                },
                "assertions": [{"type": "status_code", "expected": 200}],
                "extract": {},
            }
        )

    description = text[:1000] or "根据需求文本自动生成的场景（规则降级）"
    scenario = {"name": name, "description": description, "steps": steps}
    return {
        "source": "rule",
        "scenario": {"name": name, "description": description,
                     "step_count": len(steps)},
        "cases": [_scenario_case(name, description, steps)],
    }


def _llm_scenario(natural_language: str, project, llm_service) -> dict | None:
    messages = [
        {
            "role": "system",
            "content": (
                "你是 API 场景测试专家。请输出严格 JSON，不要输出解释。"
                '格式：{"name":"场景名","description":"","steps":[{"name":"步骤名",'
                '"request_config":{"method":"GET","url":"/path","params":{},'
                '"headers":{},"body":null},"assertions":[{"type":"status_code",'
                '"expected":200}],"extract":{}}]}'
            ),
        },
        {"role": "user", "content": f"需求：{natural_language}"},
    ]
    text = _llm_text(llm_service, messages)
    parsed = extract_first_object(text)
    if not isinstance(parsed, dict):
        return None
    steps = parsed.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    clean_steps = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        config = step.get("request_config") or step.get("request")
        if not isinstance(config, dict) or not config:
            continue
        assertions = step.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            assertions = [{"type": "status_code", "expected": 200}]
        clean_steps.append(
            {
                "name": str(step.get("name") or f"步骤{index + 1}"),
                "request_config": config,
                "assertions": [item for item in assertions if isinstance(item, dict)],
                "extract": step.get("extract") if isinstance(step.get("extract"), dict) else {},
            }
        )
    if not clean_steps:
        return None
    name = str(parsed.get("name") or "AI 生成测试场景")[:80]
    description = str(parsed.get("description") or natural_language)
    return {
        "source": "ai",
        "scenario": {"name": name, "description": description,
                     "step_count": len(clean_steps)},
        "cases": [_scenario_case(name, description, clean_steps)],
    }


def generate_scenario(natural_language, project, llm_service=None) -> dict:
    """Generate a multi-step scenario from natural language.

    Returns ``{"source": "ai"|"rule", "scenario": {...}, "cases": [...]}``.
    """
    if not str(natural_language or "").strip():
        raise BusinessError(message="需求描述不能为空", code="missing_requirement")
    if project is None:
        raise BusinessError(message="缺少 project 参数", code="missing_project")

    service = _try_llm_service(llm_service)
    if service is not None:
        try:
            generated = _llm_scenario(natural_language, project, service)
            if generated:
                return generated
            logger.info("LLM scenario generation returned nothing, using rules")
        except Exception as exc:  # noqa: BLE001 - degrade, never fail
            logger.warning("LLM scenario generation failed: %s", exc)

    return _rule_scenario(natural_language, project)
