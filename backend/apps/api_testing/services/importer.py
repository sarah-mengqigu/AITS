"""Persist parsed specifications into the database.

Keeps the API layer thin: parsing lives in ``spec_parser``, this module maps the
parsed payloads onto ``APISpecification`` / ``APIModule`` / ``APIEndpoint`` /
``APITestCase`` rows.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from apps.api_testing.models import (
    APIEndpoint,
    APIModule,
    APISpecification,
    APITestCase,
)
from apps.api_testing.services.spec_parser import decode_content, parse_openapi, parse_postman
from apps.common.api.api_exception_handler import BusinessError

logger = logging.getLogger(__name__)


def _get_or_create_module(project, spec, name, parent=None, order=0):
    module = APIModule.objects.filter(
        project=project, spec=spec, parent=parent, name=name
    ).first()
    if module is not None:
        return module, False
    module = APIModule.objects.create(
        project=project, spec=spec, parent=parent, name=name, order=order
    )
    return module, True


def _module_for_tags(spec, tags, cache):
    if not tags:
        return None
    key = ("tag", str(tags[0]))
    if key in cache:
        return cache[key]
    module, _ = _get_or_create_module(
        spec.project, spec, str(tags[0])[:128], order=len(cache)
    )
    cache[key] = module
    return module


def _module_for_folder(project, spec, folder, cache):
    parent = None
    for depth, name in enumerate(folder or []):
        name = str(name or "").strip()[:128]
        if not name:
            continue
        key = ("folder", parent.id if parent else None, name)
        if key in cache:
            parent = cache[key]
            continue
        module, _ = _get_or_create_module(
            project, spec, name, parent=parent, order=depth
        )
        cache[key] = module
        parent = module
    return parent


def _upsert_endpoint(spec, payload, module=None):
    defaults = {
        "project": spec.project,
        "module": module,
        "operation_id": payload.get("operation_id") or "",
        "summary": payload.get("summary") or payload.get("name") or "",
        "description": payload.get("description") or "",
        "parameters": payload.get("parameters") or [],
        "request_body": payload.get("request_body") or {},
        "responses": payload.get("responses") or {},
        "headers": payload.get("headers") or {},
        "is_active": True,
    }
    endpoint = APIEndpoint.objects.filter(
        spec=spec, path=payload.get("path") or "/", method=payload.get("method") or "get"
    ).first()
    if endpoint is None:
        endpoint = APIEndpoint.objects.create(
            spec=spec,
            path=payload.get("path") or "/",
            method=(payload.get("method") or "get").lower(),
            **defaults,
        )
        return endpoint, True
    for key, value in defaults.items():
        setattr(endpoint, key, value)
    endpoint.save()
    return endpoint, False


def _persist_openapi_endpoints(spec, endpoints, cache=None):
    cache = cache if cache is not None else {}
    created = 0
    updated = 0
    rows = []
    for payload in endpoints:
        module = _module_for_tags(spec, payload.get("tags"), cache)
        endpoint, is_created = _upsert_endpoint(spec, payload, module=module)
        rows.append(endpoint)
        if is_created:
            created += 1
        else:
            updated += 1
    return rows, created, updated


# ---------------------------------------------------------------------------
# OpenAPI / Swagger import
# ---------------------------------------------------------------------------
def import_openapi(
    project,
    content,
    name: str | None = None,
    base_url: str = "",
    uploaded_file=None,
    created_by=None,
) -> dict:
    """Parse and persist an OpenAPI 3 / Swagger 2 document."""
    parsed = parse_openapi(content, base_url)
    raw = content if isinstance(content, (dict, str, bytes)) else {}
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise BusinessError(message="文件编码不是 UTF-8", code="invalid_spec") from exc
    if isinstance(raw, str):
        raw = decode_content(raw)

    spec = APISpecification.objects.create(
        project=project,
        name=(name or parsed.get("title") or "未命名接口规范")[:255],
        source_type=parsed.get("source_type") or "openapi",
        version=str(parsed.get("version") or "")[:64],
        spec_data={
            "format": parsed.get("format"),
            "title": parsed.get("title"),
            "version": parsed.get("version"),
            "description": parsed.get("description"),
            "raw": raw,
        },
        file=uploaded_file,
        base_url=parsed.get("base_url") or "",
        status="parsed",
    )
    rows, created, updated = _persist_openapi_endpoints(spec, parsed.get("endpoints") or [])
    spec.endpoint_count = len(rows)
    spec.save(update_fields=["endpoint_count", "updated_at"])
    return {
        "spec": spec,
        "endpoints": rows,
        "created": created,
        "updated": updated,
        "endpoint_count": len(rows),
        "parsed": parsed,
    }


def reparse_spec(spec: APISpecification) -> dict:
    """Re-run the parser for an already imported specification."""
    if spec.source_type == "postman":
        return reparse_postman(spec)

    raw = (spec.spec_data or {}).get("raw")
    if raw is None:
        raw = (spec.spec_data or {}).get("content")
    if raw is None:
        raise BusinessError(message="规范内容缺失，无法重新解析", code="invalid_spec")
    parsed = parse_openapi(raw, spec.base_url or "")
    spec.version = str(parsed.get("version") or spec.version or "")[:64]
    if not spec.base_url:
        spec.base_url = parsed.get("base_url") or ""
    rows, created, updated = _persist_openapi_endpoints(spec, parsed.get("endpoints") or [])
    spec.endpoint_count = len(rows)
    spec.status = "parsed"
    spec.error_message = ""
    spec.save(
        update_fields=["version", "base_url", "endpoint_count", "status", "error_message",
                       "updated_at"]
    )
    return {
        "spec": spec,
        "endpoints": rows,
        "created": created,
        "updated": updated,
        "endpoint_count": len(rows),
        "parsed": parsed,
    }


# ---------------------------------------------------------------------------
# Postman import
# ---------------------------------------------------------------------------
def _infer_base_url(requests) -> str:
    for request in requests:
        raw_url = str(request.get("url") or "")
        if "{{" in raw_url:
            continue
        split = urlsplit(raw_url)
        if split.scheme and split.netloc:
            return f"{split.scheme}://{split.netloc}"
    return ""


def _postman_request_config(request: dict) -> dict:
    path = str(request.get("path") or "/")
    for key, value in (request.get("path_variables") or {}).items():
        path = path.replace(f":{key}", str(value))
    params = {
        str(param.get("name")): param.get("example")
        for param in request.get("parameters") or []
        if isinstance(param, dict) and param.get("name")
    }
    config = {
        "method": str(request.get("method") or "get").upper(),
        "url": path,
        "params": params,
        "headers": dict(request.get("headers") or {}),
    }
    body = request.get("request_body") or request.get("body")
    if isinstance(body, dict) and body:
        config["body"] = body
    return config


def _build_case_payload(request: dict) -> dict:
    assertions = [item for item in (request.get("assertions") or []) if isinstance(item, dict)]
    if not assertions:
        assertions = [{"type": "status_code", "expected": 200, "source": "postman"}]
    return {
        "name": str(request.get("name") or "Postman 请求")[:255],
        "case_type": "endpoint",
        "test_type": "positive",
        "description": request.get("description") or "由 Postman Collection 导入",
        "request_config": _postman_request_config(request),
        "assertions": assertions,
        "extract": {},
        "source": "postman",
        "priority": 2,
    }


def _persist_postman_endpoints(spec, requests, cache=None):
    cache = cache if cache is not None else {}
    rows = []
    created = 0
    updated = 0
    for request in requests:
        folder = request.get("folder") or []
        module = _module_for_folder(spec.project, spec, folder, cache) if folder else None
        payload = {
            "path": request.get("path") or "/",
            "method": str(request.get("method") or "get").lower(),
            "operation_id": "",
            "summary": request.get("name") or "",
            "description": request.get("description") or "",
            "parameters": request.get("parameters") or [],
            "request_body": request.get("request_body") or request.get("body") or {},
            "responses": {},
            "headers": request.get("headers") or {},
        }
        endpoint, is_created = _upsert_endpoint(spec, payload, module=module)
        rows.append((endpoint, request))
        if is_created:
            created += 1
        else:
            updated += 1
    return rows, created, updated


def import_postman_collection(
    project,
    collection,
    name: str | None = None,
    base_url: str = "",
    uploaded_file=None,
    created_by=None,
) -> dict:
    """Parse a Postman Collection v2.1 and persist spec + endpoints + cases."""
    requests = parse_postman(collection)
    info = collection.get("info") if isinstance(collection, dict) else {}
    info = info if isinstance(info, dict) else {}
    resolved_base_url = base_url or _infer_base_url(requests)

    spec = APISpecification.objects.create(
        project=project,
        name=(name or info.get("name") or "Postman 导入")[:255],
        source_type="postman",
        version=str(info.get("version") or info.get("schema") or "2.1")[:64],
        spec_data={
            "format": "postman",
            "title": info.get("name") or "",
            "description": info.get("description") or "",
            "collection": collection,
        },
        file=uploaded_file,
        base_url=resolved_base_url,
        status="parsed",
    )
    pairs, created, updated = _persist_postman_endpoints(spec, requests)
    cases = []
    for endpoint, request in pairs:
        payload = _build_case_payload(request)
        cases.append(
            APITestCase.objects.create(
                project=project,
                endpoint=endpoint,
                module=endpoint.module,
                **payload,
            )
        )
    spec.endpoint_count = len(pairs)
    spec.save(update_fields=["endpoint_count", "updated_at"])
    return {
        "spec": spec,
        "endpoints": [endpoint for endpoint, _ in pairs],
        "cases": cases,
        "created": created,
        "updated": updated,
        "endpoint_count": len(pairs),
        "case_count": len(cases),
        "requests": requests,
    }


def reparse_postman(spec: APISpecification) -> dict:
    collection = (spec.spec_data or {}).get("collection")
    if not isinstance(collection, dict):
        raise BusinessError(message="Postman Collection 内容缺失，无法重新解析",
                            code="invalid_collection")
    requests = parse_postman(collection)
    pairs, created, updated = _persist_postman_endpoints(spec, requests)
    spec.endpoint_count = len(pairs)
    spec.status = "parsed"
    spec.error_message = ""
    spec.save(update_fields=["endpoint_count", "status", "error_message", "updated_at"])
    return {
        "spec": spec,
        "endpoints": [endpoint for endpoint, _ in pairs],
        "created": created,
        "updated": updated,
        "endpoint_count": len(pairs),
        "requests": requests,
    }
