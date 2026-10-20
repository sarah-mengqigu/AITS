"""Locustfile generation for performance scenarios (``ARCHITECTURE`` §2.6).

The generated file must be importable Locust code, therefore everything is
validated with :func:`compile` before being returned. Supported sources:

* ``api_suite`` - one ``@task`` method per ``APITestCase`` of the suite
* ``api_case``  - one ``@task`` method for the referenced case
* ``custom_script`` - user supplied script, normalised so it always contains a
  ``HttpUser`` subclass

Comments in generated output are Chinese because operators read them in the UI.
"""

from __future__ import annotations

import keyword
import re

from apps.common.api.api_exception_handler import BusinessError

from ..constants import (
    DEFAULT_DURATION_SECONDS,
    DEFAULT_HOST,
    DEFAULT_SPAWN_RATE,
    DEFAULT_USERS,
)

SCRIPT_VALIDATION_FILENAME = "<aits-locustfile>"
DEFAULT_USER_CLASS = "AITSPerformanceUser"

#: Load settings that may be overridden through ``LoadConfiguration.config``.
#: ``error_rate`` / ``response_time_ms`` are *simulation knobs*, not load
#: settings, so they stay inside ``plan["options"]``.
SETTING_OVERRIDE_KEYS = (
    "users",
    "spawn_rate",
    "duration_seconds",
    "host",
)

_HTTP_USER_CLASS_RE = re.compile(r"class\s+\w+\s*\([^)]*HttpUser[^)]*\)")
_TASK_DECORATOR_RE = re.compile(r"@task\b")


# ---------------------------------------------------------------------------
# public helpers
# ---------------------------------------------------------------------------
def validate_script(source: str) -> str:
    """Ensure ``source`` compiles; raise :class:`BusinessError` otherwise."""
    if not isinstance(source, str) or not source.strip():
        raise BusinessError(
            message="Locust 脚本内容为空", code="empty_locust_script", status_code=400
        )
    try:
        compile(source, SCRIPT_VALIDATION_FILENAME, "exec")
    except SyntaxError as exc:
        location = f"第 {exc.lineno} 行" if exc.lineno else "未知行"
        raise BusinessError(
            message=f"Locust 脚本语法错误: {exc.msg} ({location})",
            code="invalid_locust_script",
            status_code=400,
        ) from exc
    return source


def is_locustfile(source: str) -> bool:
    """Cheap structural check used by tests / diagnostics."""
    return "HttpUser" in (source or "")


def _as_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_load_settings(scenario, config=None) -> dict:
    """Merge LoadConfiguration + inline overrides into concrete load settings."""
    config = config if config is not None else getattr(scenario, "config", None)
    variables = getattr(scenario, "variables", None) or {}

    users = DEFAULT_USERS
    spawn_rate = DEFAULT_SPAWN_RATE
    duration = DEFAULT_DURATION_SECONDS
    host = ""
    options: dict = {}

    if config is not None:
        users = getattr(config, "users", users) or users
        spawn_rate = getattr(config, "spawn_rate", spawn_rate) or spawn_rate
        duration = getattr(config, "duration_seconds", duration) or duration
        host = (getattr(config, "host", "") or "").strip() or host
        inline = getattr(config, "config", None) or {}
        if isinstance(inline, dict):
            users = inline.get("users", users)
            spawn_rate = inline.get("spawn_rate", spawn_rate)
            duration = inline.get("duration_seconds", duration)
            host = str(inline.get("host") or host)
            options = {
                key: value for key, value in inline.items()
                if key not in SETTING_OVERRIDE_KEYS
            }

    if not host:
        host = str(variables.get("host") or "").strip()
    if not host:
        host = DEFAULT_HOST

    return {
        "users": max(_as_int(users, DEFAULT_USERS), 1),
        "spawn_rate": max(_as_float(spawn_rate, DEFAULT_SPAWN_RATE), 0.1),
        "duration_seconds": max(_as_int(duration, DEFAULT_DURATION_SECONDS), 1),
        "host": host,
        "options": options,
    }


def scenario_cases(scenario) -> list:
    """Resolve the ``APITestCase`` objects a scenario is built from."""
    from apps.api_testing.models import APITestCase

    source_type = getattr(scenario, "source_type", "")
    if source_type == "api_suite":
        suite = getattr(scenario, "source_suite", None)
        if suite is None:
            return []
        case_ids = suite.ordered_case_ids() if hasattr(suite, "ordered_case_ids") else [
            int(case_id) for case_id in (suite.case_ids or [])
            if str(case_id).strip().isdigit()
        ]
        cases = {case.id: case for case in APITestCase.objects.filter(id__in=case_ids)}
        return [cases[case_id] for case_id in case_ids if case_id in cases]
    if source_type == "api_case":
        case = getattr(scenario, "source_case", None)
        return [case] if case is not None else []
    return []


def estimate_endpoint_count(scenario) -> int:
    """Best effort count of generated task methods for a scenario."""
    source_type = getattr(scenario, "source_type", "")
    if source_type in ("api_suite", "api_case"):
        return len(scenario_cases(scenario))
    script = getattr(scenario, "custom_script", "") or ""
    count = len(_TASK_DECORATOR_RE.findall(script))
    if count:
        return count
    return 1 if script.strip() else 0


# ---------------------------------------------------------------------------
# source specific rendering
# ---------------------------------------------------------------------------
def _render_variables(variables) -> str:
    value = variables if isinstance(variables, dict) else {}
    if not value:
        return "VARIABLES = {}"
    return f"VARIABLES = {value!r}"


def _substitute_variables(value, variables):
    """Replace ``${var}`` placeholders inside strings / containers."""
    if not isinstance(variables, dict) or not variables:
        return value
    if isinstance(value, str):
        result = value
        for key, replacement in variables.items():
            result = result.replace("${%s}" % key, str(replacement))
        return result
    if isinstance(value, dict):
        return {key: _substitute_variables(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute_variables(item, variables) for item in value]
    return value


def _safe_identifier(name: str, fallback: str) -> str:
    raw = (name or "").strip().lower()
    raw = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", "_", raw).strip("_")
    ident = "task_" + raw if raw and raw[0].isdigit() else raw
    if not ident:
        ident = fallback
    if keyword.iskeyword(ident):
        ident = f"{ident}_task"
    ident = re.sub(r"[^0-9a-zA-Z_]+", "_", ident).strip("_") or fallback
    if ident[0].isdigit():
        ident = f"task_{ident}"
    return ident


def _python_literal(value) -> str:
    return repr(value)


def _case_request(case, variables) -> dict:
    request = getattr(case, "request_config", None) or {}
    if not isinstance(request, dict):
        request = {}
    method = str(request.get("method") or "GET").upper()
    url = request.get("url") or request.get("path") or request.get("endpoint") or "/"
    url = str(_substitute_variables(url, variables))
    headers = _substitute_variables(request.get("headers") or {}, variables)
    params = _substitute_variables(
        request.get("params") or request.get("query") or {}, variables
    )
    body = request.get("json")
    if body is None:
        body = request.get("body")
    body = _substitute_variables(body, variables)
    form = _substitute_variables(request.get("form") or request.get("data"), variables)
    return {
        "method": method,
        "url": url,
        "headers": headers if isinstance(headers, dict) else {},
        "params": params if isinstance(params, dict) else {},
        "body": body,
        "form": form if isinstance(form, dict) else None,
    }


def _case_assertions(case) -> list:
    assertions = getattr(case, "assertions", None) or []
    if not isinstance(assertions, list):
        return []
    return [item for item in assertions if isinstance(item, dict)]


def _render_case_task(case, index: int, variables, method_ident: str) -> list[str]:
    request = _case_request(case, variables)
    assertions = _case_assertions(case)
    display = getattr(case, "name", "") or f"{request['method']} {request['url']}"
    lines = [
        f"    @task(1)",
        f"    def {method_ident}(self):",
        f"        # 用例: {display}",
    ]
    kwargs = []
    if request["headers"]:
        kwargs.append(f"headers={_python_literal(request['headers'])}")
    if request["params"]:
        kwargs.append(f"params={_python_literal(request['params'])}")
    if request["body"] is not None:
        if isinstance(request["body"], (dict, list)):
            kwargs.append(f"json={_python_literal(request['body'])}")
        else:
            kwargs.append(f"data={_python_literal(request['body'])}")
    elif request["form"]:
        kwargs.append(f"data={_python_literal(request['form'])}")
    display_name = f"{request['method']} {display}"
    kwargs.append("name=" + _python_literal(display_name))
    kwargs.append("catch_response=True")

    lines.append("        with self.client.request(")
    lines.append(f"            {_python_literal(request['method'])},")
    lines.append(f"            {_python_literal(request['url'])},")
    for kwarg in kwargs:
        lines.append(f"            {kwarg},")
    lines.append("        ) as response:")
    lines.extend(_render_assertion_checks(assertions))
    lines.append("")
    return lines


def _render_assertion_checks(assertions: list) -> list[str]:
    lines: list[str] = []
    status_expected = None
    text_expected = None
    for assertion in assertions:
        assertion_type = str(assertion.get("type") or "").lower()
        expected = assertion.get("expected", assertion.get("value"))
        if assertion_type in ("status_code", "status", "http_status"):
            status_expected = _as_int(expected, 200)
        elif assertion_type in ("contains", "text", "text_contains", "body_contains"):
            text_expected = str(expected or "")
    branch = "if"
    if status_expected is not None:
        lines.append(f"            if response.status_code != {status_expected}:")
        lines.append(
            "                response.failure("
            f"'状态码断言失败: 期望 {status_expected}, 实际 %s' % response.status_code)"
        )
        branch = "elif"
    elif not text_expected:
        lines.append("            if response.status_code >= 400:")
        lines.append(
            "                response.failure('请求失败: %s' % response.status_code)"
        )
        branch = "else"
        lines.append("            else:")
        lines.append("                response.success()")
        return lines
    if text_expected:
        lines.append(f"            {branch} {_python_literal(text_expected)} not in response.text:")
        lines.append(
            "                response.failure('响应内容断言失败: 未包含期望文本')"
        )
    lines.append("            else:")
    lines.append("                response.success()")
    return lines


def _render_api_script(scenario, cases: list, settings: dict, variables: dict) -> str:
    host = settings["host"]
    lines = [
        "from locust import HttpUser, task, between",
        "",
        f"HOST = {_python_literal(host)}",
        _render_variables(variables),
        "",
        "",
        f"class {DEFAULT_USER_CLASS}(HttpUser):",
        '    """自动生成的压测用户，按 API 套件/用例逐个接口发压。"""',
        "",
        "    host = HOST",
        "    wait_time = between(1, 3)",
        "",
    ]
    if not cases:
        lines.extend(
            [
                "    @task",
                "    def index(self):",
                '        """套件为空时的兜底任务。"""',
                '        with self.client.get("/", catch_response=True) as response:',
                "            if response.status_code >= 400:",
                "                response.failure('请求失败: %s' % response.status_code)",
                "            else:",
                "                response.success()",
                "",
            ]
        )
    else:
        used: dict[str, int] = {}
        for index, case in enumerate(cases):
            base = _safe_identifier(getattr(case, "name", ""), f"task_{index + 1}")
            count = used.get(base, 0) + 1
            used[base] = count
            ident = base if count == 1 else f"{base}_{count}"
            lines.extend(_render_case_task(case, index, variables, ident))
    return "\n".join(lines).rstrip() + "\n"


def _header_comment(scenario, settings: dict) -> list[str]:
    return [
        '"""Locustfile generated by AITS performance module.',
        "",
        f"场景: {getattr(scenario, 'name', '')}",
        f"并发用户: {settings['users']}，增长率: {settings['spawn_rate']}，"
        f"持续: {settings['duration_seconds']}s，Host: {settings['host']}",
        '"""',
    ]


def _default_custom_script(settings: dict, variables: dict) -> str:
    return "\n".join(
        [
            "from locust import HttpUser, task, between",
            "",
            f"HOST = {_python_literal(settings['host'])}",
            _render_variables(variables),
            "",
            "",
            f"class {DEFAULT_USER_CLASS}(HttpUser):",
            '    """未提供自定义脚本时的默认用户。"""',
            "",
            "    host = HOST",
            "    wait_time = between(1, 3)",
            "",
            "    @task",
            "    def index(self):",
            '        with self.client.get("/", catch_response=True) as response:',
            "            if response.status_code >= 400:",
            "                response.failure('请求失败: %s' % response.status_code)",
            "            else:",
            "                response.success()",
            "",
        ]
    )


def normalize_custom_script(source: str, settings: dict | None = None,
                            variables: dict | None = None) -> str:
    """Make a user supplied locust script importable and self consistent.

    * empty script -> generated default user
    * missing ``HttpUser`` import -> prepended
    * missing ``HttpUser`` subclass -> a default user class is appended
    """
    settings = settings or {
        "host": DEFAULT_HOST,
        "users": DEFAULT_USERS,
        "spawn_rate": DEFAULT_SPAWN_RATE,
        "duration_seconds": DEFAULT_DURATION_SECONDS,
    }
    variables = variables if isinstance(variables, dict) else {}
    text = (source or "").strip()
    if not text:
        return _default_custom_script(settings, variables)

    header = "\n".join(
        [
            '"""Locustfile generated by AITS performance module.',
            "",
            f"自定义脚本规范化: 并发用户 {settings['users']}，"
            f"增长率 {settings['spawn_rate']}，持续 {settings['duration_seconds']}s，"
            f"Host: {settings['host']}",
            '"""',
        ]
    )
    parts = [header, ""]
    body = text
    has_locust_import = re.search(
        r"^\s*(?:from\s+locust\s+import|import\s+locust)", body, re.MULTILINE
    )
    if not has_locust_import:
        parts.append("from locust import HttpUser, task, between")
        parts.append("")
    if not _HTTP_USER_CLASS_RE.search(body):
        if settings.get("host"):
            parts.extend(
                [
                    f"HOST = {_python_literal(settings['host'])}",
                    "",
                    f"class {DEFAULT_USER_CLASS}(HttpUser):",
                    "    host = HOST",
                    "    wait_time = between(1, 3)",
                    "",
                    "    @task",
                    "    def index(self):",
                    '        with self.client.get("/", catch_response=True) as response:',
                    "            if response.status_code >= 400:",
                    "                response.failure('请求失败: %s' % response.status_code)",
                    "            else:",
                    "                response.success()",
                    "",
                ]
            )
        else:
            parts.extend(
                [
                    f"class {DEFAULT_USER_CLASS}(HttpUser):",
                    "    wait_time = between(1, 3)",
                    "",
                    "    @task",
                    "    def index(self):",
                    '        with self.client.get("/", catch_response=True) as response:',
                    "            if response.status_code >= 400:",
                    "                response.failure('请求失败: %s' % response.status_code)",
                    "            else:",
                    "                response.success()",
                    "",
                ]
            )
    parts.append(body)
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------
def generate_locust_script(scenario, config=None) -> str:
    """Render a complete, compile-checked ``locustfile.py`` for ``scenario``."""
    settings = resolve_load_settings(scenario, config)
    variables = getattr(scenario, "variables", None) or {}
    if not isinstance(variables, dict):
        variables = {}
    settings["host"] = settings["host"] or str(variables.get("host") or DEFAULT_HOST)

    source_type = getattr(scenario, "source_type", "custom_script")
    if source_type == "custom_script":
        script = normalize_custom_script(
            getattr(scenario, "custom_script", "") or "", settings, variables
        )
    else:
        cases = scenario_cases(scenario)
        script = _render_api_script(scenario, cases, settings, variables)
        header = "\n".join(_header_comment(scenario, settings))
        script = header + "\n\n" + script
    return validate_script(script)


def build_plan(scenario, config=None) -> dict:
    """Build the runner plan (load settings + generated script)."""
    settings = resolve_load_settings(scenario, config)
    variables = getattr(scenario, "variables", None) or {}
    if not isinstance(variables, dict):
        variables = {}
    script = generate_locust_script(scenario, config)
    return {
        "scenario_id": getattr(scenario, "id", None),
        "scenario_name": getattr(scenario, "name", ""),
        "project_id": getattr(scenario, "project_id", None),
        "source_type": getattr(scenario, "source_type", ""),
        "endpoint_count": estimate_endpoint_count(scenario),
        "config_id": getattr(config, "id", None) if config is not None else None,
        "users": settings["users"],
        "spawn_rate": settings["spawn_rate"],
        "duration_seconds": settings["duration_seconds"],
        "host": settings["host"],
        "variables": variables,
        "options": settings.get("options") or {},
        "script": script,
    }
