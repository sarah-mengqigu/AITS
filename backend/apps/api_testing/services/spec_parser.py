"""Parsing services for OpenAPI 3 / Swagger 2 / Postman Collection v2.1.

The parsers are pure functions (no database access) so they can be unit tested
directly.  They always raise :class:`BusinessError` on invalid input - never a
bare exception that would produce a 500.
"""

from __future__ import annotations

import ast
import json
import re
from urllib.parse import parse_qsl, urlsplit

from apps.common.api.api_exception_handler import BusinessError
from apps.common.parsers.openapi import (
    api_title,
    api_version,
    base_path,
    collect_parameters,
    detect_version,
    iter_operations,
    load_text,
    request_body_schema,
    responses_summary,
)

__all__ = ["parse_openapi", "parse_postman", "substitute_variables"]

_VAR_RE = re.compile(r"\{\{\s*([\w\.\-]+)\s*\}\}")

# ``pm.response.to.have.status(200)``
_PM_STATUS_RE = re.compile(r"pm\.response\.to\.have\.status\(\s*(\d{3})\s*\)")
# ``pm.expect(pm.response.code).to.eql(200)``
_PM_RESPONSE_CODE_RE = re.compile(
    r"pm\.expect\(\s*pm\.response\.(?:code|status)\s*\)((?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*"
    r"\s*(?:\([^()]*\))?)*)"
)
# ``pm.expect(jsonData.data.id).to.eql(1)``
_PM_JSON_RE = re.compile(
    r"pm\.expect\(\s*jsonData\.([A-Za-z0-9_\.\[\]'\"]+)\s*\)"
    r"((?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*\s*(?:\([^()]*\))?)*)"
)
_CHAIN_CALL_RE = re.compile(
    r"\.\s*(eql|equal|include|contain|above|below|least|most|lengthOf|match|true|false|"
    r"empty|undefined|null|ok)\s*(?:\(([^)]*)\))?"
)
_PM_HEADER_RE = re.compile(
    r"pm\.expect\(\s*pm\.response\.to\.have\.header\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\)"
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def substitute_variables(value, variables: dict | None):
    """Recursively replace ``{{var}}`` placeholders (Postman syntax)."""
    variables = variables or {}
    if isinstance(value, str):
        def _replace(match):
            key = match.group(1)
            if key in variables:
                return str(variables[key])
            return match.group(0)

        return _VAR_RE.sub(_replace, value)
    if isinstance(value, list):
        return [substitute_variables(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: substitute_variables(item, variables) for key, item in value.items()}
    return value


def decode_content(content) -> dict:
    """Accept raw text or an already parsed mapping."""
    if isinstance(content, dict):
        return content
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise BusinessError(message="文件编码不是 UTF-8", code="invalid_spec") from exc
    if not isinstance(content, str):
        raise BusinessError(message="规范内容必须是文本", code="invalid_spec")
    return load_text(content)


def _server_base_url(spec: dict) -> str:
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"]).rstrip("/")
    return (base_path(spec) or "").rstrip("/")


# ---------------------------------------------------------------------------
# OpenAPI 3 / Swagger 2
# ---------------------------------------------------------------------------
def parse_openapi(content: str, base_url: str = "") -> dict:
    """Parse an OpenAPI 3 or Swagger 2 document.

    Returns a dict with spec metadata plus a normalised ``endpoints`` list.  The
    shape mirrors :class:`apps.api_testing.models.APIEndpoint` so the importer can
    persist it without further transformation.
    """
    spec = decode_content(content)
    try:
        version = detect_version(spec)
    except BusinessError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise BusinessError(message=f"规范解析失败: {exc}", code="invalid_spec") from exc

    resolved_base = (base_url or _server_base_url(spec) or "").rstrip("/")
    endpoints: list[dict] = []

    try:
        operations = list(iter_operations(spec))
    except BusinessError:
        raise
    except Exception as exc:
        raise BusinessError(message=f"规范操作解析失败: {exc}", code="invalid_spec") from exc

    for path, method, operation in operations:
        try:
            content_type, example, schema = request_body_schema(spec, operation, version)
            parameters = collect_parameters(spec, operation)
            responses = responses_summary(spec, operation)
        except BusinessError:
            raise
        except Exception as exc:
            raise BusinessError(
                message=f"接口 {method.upper()} {path} 解析失败: {exc}", code="invalid_spec"
            ) from exc

        headers: dict = {}
        for param in parameters:
            if param.get("in") == "header" and param.get("name"):
                headers[param["name"]] = param.get("example", "")
        if content_type:
            headers.setdefault("Content-Type", content_type)
        headers.setdefault("Accept", "application/json")

        request_body: dict = {}
        if content_type:
            request_body = {
                "content_type": content_type,
                "example": example,
                "schema": schema or {},
            }

        tags = [str(tag) for tag in (operation.get("tags") or []) if str(tag).strip()]

        endpoints.append(
            {
                "path": path,
                "method": method.lower(),
                "operation_id": operation.get("operationId") or "",
                "summary": operation.get("summary") or "",
                "description": operation.get("description") or "",
                "parameters": parameters,
                "request_body": request_body,
                "responses": responses,
                "headers": headers,
                "tags": tags,
            }
        )

    info = spec.get("info") or {}
    source_type = "swagger" if version == "swagger2" else "openapi"
    return {
        "title": api_title(spec),
        "version": api_version(spec),
        "description": info.get("description") or "",
        "source_type": source_type,
        "format": version,
        "base_url": resolved_base,
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    }


# ---------------------------------------------------------------------------
# Postman Collection v2.1
# ---------------------------------------------------------------------------
def _literal(text: str):
    """Best effort conversion of a JS literal into a Python value."""
    raw = (text or "").strip().strip("'\"")
    if raw == "":
        return ""
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        pass
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "undefined"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _assertions_from_script(script_text: str) -> list[dict]:
    """Extract status / json path assertions from a Postman test script."""
    if not script_text:
        return []
    assertions: list[dict] = []

    for match in _PM_STATUS_RE.finditer(script_text):
        assertions.append(
            {
                "type": "status_code",
                "expected": int(match.group(1)),
                "source": "postman",
                "description": "pm.response.to.have.status",
            }
        )

    for match in _PM_RESPONSE_CODE_RE.finditer(script_text):
        expected = _first_chain_value(match.group(1))
        if expected is not None:
            assertions.append(
                {
                    "type": "status_code",
                    "expected": _literal(str(expected)),
                    "source": "postman",
                    "description": "pm.expect(pm.response.code)",
                }
            )

    for match in _PM_JSON_RE.finditer(script_text):
        path = _normalise_json_path(match.group(1))
        chain = match.group(2) or ""
        call = _CHAIN_CALL_RE.search(chain)
        if not call:
            continue
        name = call.group(1)
        args = call.group(2)
        if name in ("eql", "equal"):
            assertions.append(
                {
                    "type": "json_path",
                    "path": path,
                    "expected": _literal(args or ""),
                    "source": "postman",
                    "description": "pm.expect(jsonData)",
                }
            )
        elif name in ("include", "contain"):
            assertions.append(
                {
                    "type": "contains",
                    "path": path,
                    "expected": _literal(args or ""),
                    "source": "postman",
                    "description": "pm.expect(jsonData).include",
                }
            )
        elif name in ("above", "least"):
            assertions.append(
                {
                    "type": "len_gte",
                    "path": path,
                    "expected": _literal(args or ""),
                    "source": "postman",
                    "description": "pm.expect(jsonData) above",
                }
            )
        elif name in ("lengthOf", "most"):
            assertions.append(
                {
                    "type": "len_gte",
                    "path": path,
                    "expected": _literal(args or ""),
                    "source": "postman",
                    "description": "pm.expect(jsonData).lengthOf",
                }
            )
        elif name == "true":
            assertions.append(
                {
                    "type": "json_path",
                    "path": path,
                    "expected": True,
                    "source": "postman",
                    "description": "pm.expect(jsonData).to.be.true",
                }
            )
        elif name == "false":
            assertions.append(
                {
                    "type": "json_path",
                    "path": path,
                    "expected": False,
                    "source": "postman",
                    "description": "pm.expect(jsonData).to.be.false",
                }
            )

    for match in _PM_HEADER_RE.finditer(script_text):
        assertions.append(
            {
                "type": "header_present",
                "expected": match.group(1),
                "source": "postman",
                "description": "pm.response.to.have.header",
            }
        )
    return assertions


def _first_chain_value(chain: str):
    call = _CHAIN_CALL_RE.search(chain or "")
    if not call:
        return None
    return call.group(2)


def _normalise_json_path(path: str) -> str:
    """``data['id']`` -> ``data.id``; keep numeric indexes."""
    path = (path or "").strip()
    path = re.sub(r"\[\s*['\"]([^'\"]+)['\"]\s*\]", r".\1", path)
    path = re.sub(r"\[\s*(\d+)\s*\]", r".\1", path)
    return path.strip(".")


def _iter_items(items, folder: list[str], inherited_auth, variables: dict):
    """Depth first walk of ``collection.item`` preserving document order."""
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("item"), list):
            name = item.get("name") or "未命名目录"
            yield from _iter_items(item["item"], folder + [name],
                                   item.get("auth") or inherited_auth, variables)
            continue
        request = item.get("request")
        if request is None:
            continue
        yield _parse_request(item, request, folder, inherited_auth, variables)


def _request_url(request: dict) -> tuple[str, dict, str]:
    """Return ``(raw_url, url_object, base_url)`` for a Postman request."""
    url = request.get("url")
    if isinstance(url, str):
        return url, {}, ""
    if not isinstance(url, dict):
        return "", {}, ""
    raw = url.get("raw")
    if not raw:
        host = url.get("host")
        if isinstance(host, list):
            host = ".".join(str(part) for part in host)
        protocol = (url.get("protocol") or "https") + "://" if host else ""
        path = url.get("path")
        if isinstance(path, list):
            path = "/" + "/".join(str(part) for part in path)
        raw = f"{protocol}{host or ''}{path or ''}"
    return str(raw), url, ""


def _parse_request(item: dict, request, folder: list[str], inherited_auth,
                   variables: dict) -> dict:
    if isinstance(request, str):
        request = {"url": request, "method": "GET"}
    if not isinstance(request, dict):
        request = {}

    raw_url, url_obj, _ = _request_url(request)
    raw_url = substitute_variables(raw_url, variables)
    method = str(request.get("method") or "GET").lower()

    split = urlsplit(raw_url)
    path = split.path or "/"
    if not path.startswith("/"):
        path = "/" + path

    params: list[dict] = []
    raw_query = split.query
    query_items = url_obj.get("query") if isinstance(url_obj, dict) else None
    if isinstance(query_items, list) and query_items:
        for entry in query_items:
            if not isinstance(entry, dict) or entry.get("disabled"):
                continue
            params.append(
                {
                    "name": substitute_variables(str(entry.get("key", "")), variables),
                    "in": "query",
                    "required": not bool(entry.get("disabled")),
                    "type": "string",
                    "example": substitute_variables(entry.get("value"), variables),
                    "description": entry.get("description") or "",
                }
            )
    elif raw_query:
        for key, value in parse_qsl(raw_query, keep_blank_values=True):
            params.append(
                {
                    "name": key,
                    "in": "query",
                    "required": True,
                    "type": "string",
                    "example": value,
                    "description": "",
                }
            )

    path_variables: dict = {}
    url_variable = url_obj.get("variable") if isinstance(url_obj, dict) else None
    for entry in url_variable or []:
        if isinstance(entry, dict) and entry.get("key"):
            path_variables[str(entry["key"])] = substitute_variables(
                entry.get("value"), variables
            )

    headers: dict = {}
    for entry in request.get("header") or []:
        if not isinstance(entry, dict) or entry.get("disabled"):
            continue
        key = str(entry.get("key") or "").strip()
        if not key:
            continue
        headers[key] = substitute_variables(entry.get("value") or "", variables)

    body: dict = {}
    raw_body = request.get("body")
    if isinstance(raw_body, dict) and raw_body.get("mode"):
        mode = raw_body.get("mode")
        body["mode"] = mode
        if mode == "raw":
            text = substitute_variables(raw_body.get("raw") or "", variables)
            body["raw"] = text
            language = ((raw_body.get("options") or {}).get("raw") or {}).get("language")
            if language:
                body["language"] = language
            if language == "json" or _looks_like_json(text):
                parsed = _try_json(text)
                if parsed is not None:
                    body["json"] = parsed
            headers.setdefault("Content-Type", "application/json"
                               if language == "json" else "text/plain")
        elif mode == "urlencoded":
            form = {}
            for entry in raw_body.get("urlencoded") or []:
                if isinstance(entry, dict) and not entry.get("disabled"):
                    form[str(entry.get("key"))] = substitute_variables(
                        entry.get("value"), variables
                    )
            body["urlencoded"] = form
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif mode == "formdata":
            form = {}
            files: list[str] = []
            for entry in raw_body.get("formdata") or []:
                if not isinstance(entry, dict) or entry.get("disabled"):
                    continue
                if entry.get("type") == "file":
                    files.append(str(entry.get("key")))
                form[str(entry.get("key"))] = substitute_variables(
                    entry.get("value"), variables
                )
            body["formdata"] = form
            if files:
                body["files"] = files
            headers.setdefault("Content-Type", "multipart/form-data")
        elif mode == "graphql":
            graphql = raw_body.get("graphql") or {}
            body["graphql"] = substitute_variables(graphql, variables)
            headers.setdefault("Content-Type", "application/json")
        elif mode == "file":
            body["file"] = raw_body.get("file") or {}

    script_lines: list[str] = []
    for event in item.get("event") or []:
        if not isinstance(event, dict) or event.get("listen") != "test":
            continue
        script = event.get("script") or {}
        exec_lines = script.get("exec") if isinstance(script, dict) else None
        if isinstance(exec_lines, str):
            script_lines.append(exec_lines)
        elif isinstance(exec_lines, list):
            script_lines.append("\n".join(str(line) for line in exec_lines))

    assertions = _assertions_from_script("\n".join(script_lines))
    auth = request.get("auth") or inherited_auth

    name = item.get("name") or f"{method.upper()} {path}"
    description = request.get("description") or ""

    return {
        "name": name,
        "method": method,
        "path": path,
        "url": raw_url,
        "folder": list(folder),
        "headers": headers,
        "parameters": params,
        "path_variables": path_variables,
        "request_body": body,
        "body": body,
        "auth": auth or {},
        "assertions": assertions,
        "description": description,
        "source": "postman",
        "test_script": "\n".join(script_lines),
    }


def _looks_like_json(text: str) -> bool:
    stripped = (text or "").strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _try_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_postman(collection: dict, variables: dict | None = None) -> list[dict]:
    """Parse a Postman Collection v2.1 into a flat list of request dicts.

    Supports nested folders, ``{{variable}}`` interpolation, url/query/path,
    headers, raw/urlencoded/formdata bodies, auth pass-through and converts
    ``pm.test`` scripts into AITS assertions.
    """
    if isinstance(collection, (str, bytes)):
        try:
            collection = decode_content(collection)
        except BusinessError:
            raise BusinessError(message="Postman Collection 不是合法 JSON", code="invalid_collection")
    if not isinstance(collection, dict):
        raise BusinessError(message="Postman Collection 必须是 JSON 对象", code="invalid_collection")
    if "item" not in collection and "info" not in collection:
        raise BusinessError(
            message="不是合法的 Postman Collection（缺少 item/info）", code="invalid_collection"
        )
    if not isinstance(collection.get("item"), list):
        raise BusinessError(
            message="Postman Collection 缺少 item 列表", code="invalid_collection"
        )

    merged_vars: dict = {}
    for entry in collection.get("variable") or []:
        if isinstance(entry, dict) and entry.get("key"):
            merged_vars[str(entry["key"])] = entry.get("value")
    if isinstance(variables, dict):
        merged_vars.update(variables)

    requests: list[dict] = []
    try:
        for parsed in _iter_items(collection.get("item"), [], collection.get("auth"), merged_vars):
            requests.append(parsed)
    except BusinessError:
        raise
    except Exception as exc:
        raise BusinessError(
            message=f"Postman Collection 解析失败: {exc}", code="invalid_collection"
        ) from exc

    if not requests:
        raise BusinessError(
            message="Postman Collection 中没有可导入的请求", code="empty_collection"
        )
    return requests
