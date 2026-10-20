"""api_testcase Agent：根据 API 端点生成正向/负向/边界/安全 4 类用例。"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from apps.ai_core.services.agents.base import BaseAgent


class APITestCaseState(TypedDict, total=False):
    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    result: Any


TEST_TYPES = ("positive", "negative", "boundary", "security")


def _schema_sample(schema, depth: int = 0) -> Any:
    if not isinstance(schema, dict) or depth > 3:
        return "test"
    if schema.get("enum"):
        return schema["enum"][0]
    if "example" in schema:
        return schema["example"]
    if "default" in schema and schema["default"] is not None:
        return schema["default"]
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = schema_type[0] if schema_type else None
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        item_schema = schema.get("items") or {}
        return [_schema_sample(item_schema, depth + 1)]
    if schema_type == "object":
        return {
            name: _schema_sample(spec, depth + 1)
            for name, spec in (schema.get("properties") or {}).items()
        }
    return "test"


def _body_schema(request_body) -> dict:
    if not isinstance(request_body, dict):
        return {}
    content = request_body.get("content")
    if isinstance(content, dict):
        for content_type in ("application/json", "application/*+json"):
            if content_type in content and isinstance(content[content_type], dict):
                return content[content_type].get("schema") or {}
        for value in content.values():
            if isinstance(value, dict) and value.get("schema"):
                return value["schema"]
    return request_body.get("schema") or request_body


def _sample_body(request_body) -> Any:
    schema = _body_schema(request_body)
    if not schema:
        return None
    if schema.get("type") == "object" or schema.get("properties"):
        return {
            name: _schema_sample(spec)
            for name, spec in (schema.get("properties") or {}).items()
        }
    return _schema_sample(schema)


def _param_samples(parameters) -> dict:
    samples = {}
    for parameter in parameters or []:
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("name")
        if not name:
            continue
        samples[name] = parameter.get("example", _schema_sample(parameter.get("schema") or {}))
    return samples


def _first_string_key(mapping: dict) -> str | None:
    for key, value in (mapping or {}).items():
        if isinstance(value, str):
            return key
    return None


def build_endpoint_cases(endpoint: dict) -> list[dict]:
    """Deterministic 4-type cases derived from method / parameters / request_body."""
    endpoint = endpoint or {}
    method = str(endpoint.get("method") or "GET").upper()
    path = endpoint.get("path") or endpoint.get("url") or "/"
    parameters = endpoint.get("parameters") or []
    body_sample = _sample_body(endpoint.get("request_body"))
    params = _param_samples(parameters)
    required = [
        parameter.get("name")
        for parameter in parameters or []
        if isinstance(parameter, dict) and parameter.get("required") and parameter.get("name")
    ]
    string_key = _first_string_key(params) or _first_string_key(body_sample or {}) or "keyword"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    positive_request = {
        "method": method,
        "path": path,
        "headers": dict(headers),
        "params": dict(params),
        "body": body_sample,
    }

    negative_params = dict(params)
    if required:
        negative_params.pop(required[0], None)
    negative_body = json.loads(json.dumps(body_sample)) if body_sample else {"invalid": True}
    if isinstance(negative_body, dict) and required:
        negative_body.pop(required[0], None)
    else:
        negative_body = {"__invalid__": True}

    boundary_params = dict(params)
    boundary_params[string_key] = "x" * 500
    boundary_body = None
    if body_sample is not None:
        boundary_body = json.loads(json.dumps(body_sample))
        if isinstance(boundary_body, dict):
            if string_key in boundary_body:
                boundary_body[string_key] = "x" * 500
            elif boundary_body:
                boundary_body[next(iter(boundary_body))] = "x" * 500
    else:
        boundary_params[string_key] = "9" * 400

    security_params = dict(params)
    security_params[string_key] = "' OR 1=1 --"
    security_headers = dict(headers)
    security_headers["X-Injection"] = "<script>alert(1)</script>"

    return [
        {
            "name": "正常参数请求",
            "case_type": "endpoint",
            "test_type": "positive",
            "description": f"{method} {path} 使用合法参数应返回成功",
            "request": positive_request,
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "response_time", "operator": "lt", "expected": 3000},
            ],
        },
        {
            "name": "缺失必填参数",
            "case_type": "endpoint",
            "test_type": "negative",
            "description": "缺少必填参数或传非法类型时应返回 4xx",
            "request": {
                "method": method,
                "path": path,
                "headers": dict(headers),
                "params": negative_params,
                "body": negative_body,
            },
            "assertions": [
                {"type": "status_code", "operator": "in", "expected": [400, 422]},
                {"type": "json_path", "operator": "exists", "expected": "message"},
            ],
        },
        {
            "name": "边界值参数",
            "case_type": "endpoint",
            "test_type": "boundary",
            "description": "超长/超大边界值应被服务端正确拒绝或截断",
            "request": {
                "method": method,
                "path": path,
                "headers": dict(headers),
                "params": boundary_params,
                "body": boundary_body,
            },
            "assertions": [
                {"type": "status_code", "operator": "in", "expected": [400, 422]},
            ],
        },
        {
            "name": "越权与注入攻击",
            "case_type": "endpoint",
            "test_type": "security",
            "description": "SQL 注入 / XSS / 未授权访问应被拦截",
            "request": {
                "method": method,
                "path": path,
                "headers": security_headers,
                "params": security_params,
                "body": body_sample,
                "no_auth": True,
            },
            "assertions": [
                {"type": "status_code", "operator": "in", "expected": [401, 403, 400]},
                {"type": "body_not_contains", "expected": "SQL"},
            ],
        },
    ]


class APITestCaseAgent(BaseAgent):
    name = "api_testcase"
    description = "根据 API 端点信息生成正向/负向/边界/安全四类接口测试用例"
    stream_channel = "api_testcase_generation"
    task_type = "api_testcase"
    state_schema = APITestCaseState

    def retrieval_query(self, state) -> str:
        endpoint = (state.get("payload") or {}).get("endpoint") or {}
        return " ".join(
            str(part)
            for part in (
                endpoint.get("summary"),
                endpoint.get("path"),
                endpoint.get("description"),
                (state.get("payload") or {}).get("context"),
            )
            if part
        )

    def build_prompt(self, payload: dict) -> str:
        endpoint = payload.get("endpoint") or {}
        context = payload.get("context") or ""
        return (
            f"[agent:{self.name}]\n"
            "请为下面的 API 端点生成 4 类测试用例：positive / negative / boundary / security。\n"
            "每类用例包含 name、case_type、test_type、request(method/path/headers/params/body)、"
            "assertions。\n"
            f"端点定义：{json.dumps(endpoint, ensure_ascii=False, default=str)}\n"
            f"补充上下文：{context}\n"
            '仅返回 JSON：{"cases": [...]}'
        )

    def compose_result(self, payload: dict, llm_data, state) -> dict:
        endpoint = payload.get("endpoint") or {}
        rule_cases = build_endpoint_cases(endpoint)
        llm_cases: list[dict] = []
        if isinstance(llm_data, dict):
            raw = llm_data.get("cases")
            if isinstance(raw, list):
                llm_cases = [case for case in raw if isinstance(case, dict)]
        by_type: dict[str, dict] = {}
        for case in llm_cases:
            test_type = case.get("test_type")
            if test_type in TEST_TYPES and test_type not in by_type:
                by_type[test_type] = case

        cases = []
        for index, rule_case in enumerate(rule_cases):
            merged = dict(rule_case)
            llm_case = by_type.get(rule_case["test_type"])
            if llm_case:
                merged["name"] = str(llm_case.get("name") or rule_case["name"])
                merged["description"] = str(
                    llm_case.get("description") or rule_case["description"]
                )
                if isinstance(llm_case.get("assertions"), list) and llm_case["assertions"]:
                    merged["assertions"] = llm_case["assertions"]
                if isinstance(llm_case.get("request"), dict):
                    request = dict(rule_case["request"])
                    for key in ("headers", "params", "body"):
                        if llm_case["request"].get(key):
                            request[key] = llm_case["request"][key]
                    # endpoint derived method/path always win
                    request["method"] = rule_case["request"]["method"]
                    request["path"] = rule_case["request"]["path"]
                    merged["request"] = request
            merged["id"] = f"case-{index + 1}"
            cases.append(merged)
        return {
            "cases": cases,
            "endpoint": {
                "method": str(endpoint.get("method") or "GET").upper(),
                "path": endpoint.get("path") or endpoint.get("url") or "/",
            },
        }
