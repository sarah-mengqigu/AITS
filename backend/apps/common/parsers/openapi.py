"""Minimal, dependency free OpenAPI 3 / Swagger 2 loader.

The importer only needs a predictable intermediate representation; this module
normalises both spec dialects into the same shape consumed by
``apps.api_testing.services.spec_parser``.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from apps.common.api.api_exception_handler import BusinessError

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


def load_text(text: str) -> dict:
    """Load a spec from JSON or YAML text."""
    if not text or not text.strip():
        raise BusinessError(message="文件内容为空", code="empty_spec")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise BusinessError(message=f"JSON 规范解析失败: {exc}", code="invalid_spec")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BusinessError(message=f"YAML 规范解析失败: {exc}", code="invalid_spec")
    if not isinstance(data, dict):
        raise BusinessError(message="规范根节点必须是对象", code="invalid_spec")
    return data


def detect_version(spec: dict) -> str:
    if str(spec.get("openapi", "")).startswith("3"):
        return "openapi3"
    if str(spec.get("swagger", "")).startswith("2"):
        return "swagger2"
    if "paths" in spec:
        return "openapi3"  # best effort
    raise BusinessError(message="无法识别规范版本（需 OpenAPI3 或 Swagger2）", code="unknown_spec")


def api_title(spec: dict) -> str:
    info = spec.get("info") or {}
    return info.get("title") or "未命名接口规范"


def api_version(spec: dict) -> str:
    info = spec.get("info") or {}
    return str(info.get("version") or "")


def base_path(spec: dict) -> str:
    if "basePath" in spec:
        return spec.get("basePath") or ""
    servers = spec.get("servers") or []
    if servers and isinstance(servers, list):
        return ""
    return ""


def resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a local ``#/components/...`` or ``#/definitions/...`` reference."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {}
    node: Any = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}


def deref(spec: dict, node, depth: int = 0):
    """Recursively dereference ``$ref`` (bounded depth to avoid cycles)."""
    if depth > 6:
        return node
    if isinstance(node, dict):
        if "$ref" in node:
            target = resolve_ref(spec, node["$ref"])
            merged = dict(target)
            merged.update({k: v for k, v in node.items() if k != "$ref"})
            return deref(spec, merged, depth + 1)
        return {key: deref(spec, value, depth + 1) for key, value in node.items()}
    if isinstance(node, list):
        return [deref(spec, item, depth + 1) for item in node]
    return node


def _resolve_schema(spec: dict, schema) -> dict:
    if isinstance(schema, dict) and "$ref" in schema:
        return deref(spec, schema)
    return schema or {}


def example_from_schema(spec: dict, schema: dict | None):
    """Generate a deterministic example value for a JSON schema."""
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if "allOf" in schema and schema["allOf"]:
        merged: dict = {}
        for sub in schema["allOf"]:
            example = example_from_schema(spec, _resolve_schema(spec, sub))
            if isinstance(example, dict):
                merged.update(example)
        return merged
    if "oneOf" in schema and schema["oneOf"]:
        return example_from_schema(spec, _resolve_schema(spec, schema["oneOf"][0]))
    if "anyOf" in schema and schema["anyOf"]:
        return example_from_schema(spec, _resolve_schema(spec, schema["anyOf"][0]))

    stype = schema.get("type")
    if isinstance(stype, list):
        stype = next((t for t in stype if t != "null"), "string")
    if stype == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        return {name: example_from_schema(spec, _resolve_schema(spec, sub))
                for name, sub in props.items()}
    if stype == "array":
        item = _resolve_schema(spec, schema.get("items")) if schema.get("items") else {}
        return [example_from_schema(spec, item)]
    if stype == "integer":
        return 1
    if stype == "number":
        return 1.0
    if stype == "boolean":
        return True
    if stype == "string":
        fmt = schema.get("format")
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "email":
            return "user@example.com"
        if fmt in ("int64", "uuid"):
            return "00000000-0000-0000-0000-000000000000" if fmt == "uuid" else "1"
        return "string"
    return None


def iter_operations(spec: dict):
    """Yield ``(path, method, operation)`` for every operation in the spec."""
    paths = spec.get("paths") or {}
    if not isinstance(paths, dict):
        return
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            operation = item.get(method)
            if isinstance(operation, dict):
                yield path, method, operation


def request_body_schema(spec: dict, operation: dict, version: str):
    """Return ``(content_type, example_body, schema)`` for the operation."""
    if version == "swagger2":
        body_param = next(
            (p for p in operation.get("parameters", []) if p.get("in") == "body"), None
        )
        if body_param:
            schema = _resolve_schema(spec, body_param.get("schema"))
            return (
                "application/json",
                body_param.get("example") or example_from_schema(spec, schema),
                schema,
            )
        form_param = next(
            (p for p in operation.get("parameters", []) if p.get("in") == "formData"), None
        )
        if form_param:
            form_schema = {
                "type": "object",
                "properties": {
                    p["name"]: p.get("schema") or {"type": p.get("type", "string")}
                    for p in operation.get("parameters", [])
                    if p.get("in") == "formData"
                },
            }
            return (
                "multipart/form-data",
                example_from_schema(spec, form_schema),
                form_schema,
            )
        return None, None, None

    body = operation.get("requestBody") or {}
    content = body.get("content") or {}
    for content_type in ("application/json", "application/x-www-form-urlencoded",
                         "multipart/form-data", "text/plain"):
        if content_type in content:
            media = content[content_type] or {}
            schema = _resolve_schema(spec, media.get("schema"))
            example = media.get("example")
            if example is None:
                example = example_from_schema(spec, schema)
            return content_type, example, schema
    return None, None, None


def responses_summary(spec: dict, operation: dict) -> dict:
    """Return ``{status_code: schema}`` for documented responses."""
    result = {}
    responses = operation.get("responses") or {}
    if not isinstance(responses, dict):
        return result
    for code, response in responses.items():
        if not isinstance(response, dict):
            continue
        if "schema" in response:  # swagger2
            result[str(code)] = deref(spec, response["schema"])
            continue
        content = response.get("content") or {}
        media = content.get("application/json") or next(iter(content.values()), {})
        schema = media.get("schema") if isinstance(media, dict) else None
        result[str(code)] = deref(spec, schema) if schema else {}
    return result


def collect_parameters(spec: dict, operation: dict) -> list[dict]:
    params = []
    for raw in operation.get("parameters") or []:
        if not isinstance(raw, dict):
            continue
        raw = deref(spec, raw)
        params.append(
            {
                "name": raw.get("name"),
                "in": raw.get("in", "query"),
                "required": bool(raw.get("required", False)),
                "type": (raw.get("schema") or {}).get("type") or raw.get("type") or "string",
                "example": raw.get("example")
                or example_from_schema(spec, raw.get("schema") or {}),
                "description": raw.get("description", ""),
            }
        )
    return params
