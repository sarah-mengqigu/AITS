"""Sonic (移动端自动化测试平台) HTTP 客户端.

设计要点
--------
* 默认值全部来自 ``settings.SONIC_*``（``SONIC_BASE_URL`` / ``SONIC_API_PREFIX``
  / ``SONIC_USERNAME`` / ``SONIC_PASSWORD`` / ``SONIC_TOKEN`` / ``SONIC_TIMEOUT``）。
* Token 自动登录 + 续期：登录成功的 token 缓存到 Django cache
  ``sonic:token:{base_url}``；HTTP 401/403 时清缓存后**自动重登一次**再重试请求。
* 登录接口对 ``{"userName","password"}`` 与 ``{"username","password"}`` 两种 body
  都做了尝试（不同 Sonic 版本字段不同）。
* 业务码映射（``SonicAPIError``）：``3001 -> 套件不存在``、``3002 -> 套件内无
  用例``、``3003 -> 无在线设备``，其它业务码返回服务端原始 message。
* 网络/HTTP 层异常统一转 ``BusinessError(code="sonic_unavailable", status_code=503)``。
* **未配置 ``SONIC_BASE_URL``**：读接口返回空列表（不报错），写/运行动作抛
  ``BusinessError(code="sonic_not_configured")``；任何情况下都不会 500。
* 所有 HTTP 都走注入的 ``session``（.request）或 ``requests.request``，单测里通过
  ``patch("apps.app_testing.services.sonic_client.requests")`` 打桩，不访问网络。
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.cache import cache

from apps.common.api.api_exception_handler import BusinessError

logger = logging.getLogger(__name__)

#: Sonic 业务错误码 -> 中文提示
BIZ_CODE_MESSAGES = {
    3001: "套件不存在",
    3002: "套件内无用例",
    3003: "无在线设备",
}

#: 视为成功的业务码（Sonic 不同版本：0 / 200 / 2000 / 20000）
SUCCESS_BIZ_CODES = {0, 200, 2000, 20000, "0", "200", "2000", "20000"}

TOKEN_CACHE_PREFIX = "sonic:token:"

#: 相对 ``SONIC_API_PREFIX`` 的接口路径（集中定义便于适配不同 Sonic 版本）
ENDPOINTS = {
    "login": "/auth/login",
    "projects": "/projects",
    "devices": "/devices/list",
    "device": "/devices/{udid}",
    "device_remote": "/devices/{udid}/remote",
    "element_pages": "/elements/pages",
    "test_suites": "/testSuites",
    "run_suite": "/remote/runSuite",
    "suite_result": "/testSuites/{suite_id}/result",
}

#: 登录 body 的两种字段风格（按顺序尝试）
LOGIN_BODY_VARIANTS = (
    lambda username, password: {"userName": username, "password": password},
    lambda username, password: {"username": username, "password": password},
)


class SonicAPIError(Exception):
    """Sonic 业务错误（HTTP 层成功但业务码失败）。"""

    def __init__(self, code=None, message="Sonic 接口返回错误", biz_code=None):
        self.code = code
        self.message = message
        self.biz_code = biz_code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def map_biz_message(biz_code, fallback="") -> str:
    """Business code -> Chinese message (``3001/3002/3003`` are mapped)."""
    return BIZ_CODE_MESSAGES.get(biz_code) or fallback or "Sonic 接口返回错误"


class SonicClient:
    """Thin, fault tolerant Sonic HTTP client.

    ``base_url`` / ``username`` / ``password`` / ``timeout`` default to the
    Django settings so callers usually just do ``SonicClient()``.
    """

    def __init__(self, base_url=None, username=None, password=None, timeout=None,
                 session=None, token=None):
        self.base_url = (base_url if base_url is not None
                         else getattr(settings, "SONIC_BASE_URL", "") or "").strip().rstrip("/")
        self.api_prefix = (getattr(settings, "SONIC_API_PREFIX", "/server/api") or "").rstrip("/")
        self.username = (username if username is not None
                         else getattr(settings, "SONIC_USERNAME", "") or "")
        self.password = (password if password is not None
                         else getattr(settings, "SONIC_PASSWORD", "") or "")
        self.timeout = float(
            timeout if timeout is not None
            else getattr(settings, "SONIC_TIMEOUT", 15) or 15
        )
        self.session = session
        self._explicit_token = (
            token if token is not None else getattr(settings, "SONIC_TOKEN", "") or ""
        )
        #: Sonic 项目 ID（由 ``get_sonic_client(project)`` 填充，也用于默认项目）
        self.project_id = getattr(settings, "SONIC_PROJECT_ID", "") or ""

    # ------------------------------------------------------------------
    # configuration helpers
    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def token_cache_key(self) -> str:
        return f"{TOKEN_CACHE_PREFIX}{self.base_url}"

    def _require_configured(self, action="调用"):
        if not self.configured:
            raise BusinessError(
                message="未配置 Sonic 服务，请先在环境变量中设置 SONIC_BASE_URL",
                code="sonic_not_configured",
            )

    def _url(self, name_or_path: str, **fmt) -> str:
        path = ENDPOINTS.get(name_or_path, name_or_path).format(**fmt)
        return f"{self.base_url}{self.api_prefix}{path}"

    # ------------------------------------------------------------------
    # low level http
    # ------------------------------------------------------------------
    def _send(self, method, url, **kwargs):
        """Perform one HTTP request; transport failures -> ``sonic_unavailable``."""
        kwargs.setdefault("timeout", self.timeout)
        try:
            if self.session is not None:
                response = self.session.request(method, url, **kwargs)
            else:
                response = requests.request(method, url, **kwargs)
        except Exception as exc:  # requests.RequestException (or a stub) -> 503
            logger.warning("sonic request failed: %s %s (%s)", method, url, exc)
            raise BusinessError(
                message=f"Sonic 服务不可用: {exc}",
                code="sonic_unavailable",
                status_code=503,
            ) from exc
        return response

    @staticmethod
    def _json(response):
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - invalid JSON body
            payload = None
        return payload if isinstance(payload, (dict, list)) else None

    @staticmethod
    def _status_code(response) -> int:
        return int(getattr(response, "status_code", 0) or 0)

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------
    def _login(self) -> str:
        """Login and return a token; tries both body field conventions."""
        self._require_configured()
        url = self._url("login")
        last_error = None
        for build_body in LOGIN_BODY_VARIANTS:
            try:
                response = self._send("post", url, json=build_body(self.username, self.password))
            except BusinessError as exc:
                last_error = exc
                continue
            token = self._extract_token(self._json(response))
            if token:
                cache.set(self.token_cache_key, token, timeout=3600 * 6)
                self._explicit_token = token
                return token
            status_code = self._status_code(response)
            if status_code in (401, 403):
                last_error = SonicAPIError(
                    code=status_code, message="Sonic 登录失败，请检查账号密码",
                    biz_code=status_code,
                )
            else:
                payload = self._json(response) or {}
                message = payload.get("message") if isinstance(payload, dict) else ""
                last_error = SonicAPIError(
                    code=status_code or 1, message=message or "Sonic 登录失败",
                    biz_code=payload.get("code") if isinstance(payload, dict) else None,
                )
        if isinstance(last_error, BusinessError):
            raise last_error
        raise last_error or SonicAPIError(message="Sonic 登录失败")

    @staticmethod
    def _extract_token(payload) -> str:
        if not isinstance(payload, dict):
            return ""
        data = payload.get("data")
        for container in (payload, data if isinstance(data, dict) else {}):
            for key in ("token", "accessToken", "access_token"):
                value = container.get(key)
                if isinstance(value, str) and value:
                    return value
        # some versions nest one more level: {"data": {"data": {"token": ...}}}
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            return SonicClient._extract_token({"data": data["data"]})
        return ""

    def get_token(self, force_refresh=False) -> str:
        """Return a cached token, logging in on demand."""
        self._require_configured()
        if not force_refresh:
            cached = cache.get(self.token_cache_key)
            if cached:
                return cached
            if self._explicit_token:
                cache.set(self.token_cache_key, self._explicit_token, timeout=3600 * 6)
                return self._explicit_token
        return self._login()

    def invalidate_token(self) -> None:
        cache.delete(self.token_cache_key)
        self._explicit_token = ""

    def _headers(self) -> dict:
        token = self.get_token()
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    # ------------------------------------------------------------------
    # request with automatic re-login on 401/403
    # ------------------------------------------------------------------
    def request(self, method, url_name, **kwargs):
        """JSON request with one transparent re-login on 401/403.

        ``udid`` / ``suite_id`` are URL path parameters and are removed from the
        request keyword arguments before sending.
        """
        self._require_configured()
        fmt = {key: kwargs.pop(key) for key in ("udid", "suite_id") if key in kwargs}
        url = self._url(url_name, **fmt)
        headers = dict(kwargs.pop("headers", None) or {})
        headers.update(self._headers())
        response = self._send(method, url, headers=headers, **kwargs)
        if self._status_code(response) in (401, 403):
            logger.info("sonic token expired/invalid, re-login once")
            self.invalidate_token()
            headers = dict(kwargs.get("headers", None) or {})
            headers.update(self._headers())
            response = self._send(method, url, headers=headers, **kwargs)
        return response

    def _payload(self, response, allow_list=False):
        """Validate one Sonic response -> ``data`` or a Python list."""
        status_code = self._status_code(response)
        payload = self._json(response)
        if status_code in (401, 403):
            raise SonicAPIError(
                code=status_code, message="Sonic 鉴权失败，请检查账号密码",
                biz_code=status_code,
            )
        if status_code and (status_code < 200 or status_code >= 300):
            message = ""
            if isinstance(payload, dict):
                message = payload.get("message") or ""
            raise SonicAPIError(
                code=status_code, message=message or f"Sonic 接口异常(HTTP {status_code})",
                biz_code=payload.get("code") if isinstance(payload, dict) else None,
            )
        if allow_list and isinstance(payload, list):
            return payload
        if payload is None:
            raise SonicAPIError(code=status_code, message="Sonic 接口返回非 JSON 数据")
        if isinstance(payload, dict):
            biz_code = payload.get("code")
            if biz_code is not None and biz_code not in SUCCESS_BIZ_CODES:
                raise SonicAPIError(
                    code=biz_code,
                    message=map_biz_message(biz_code, payload.get("message") or ""),
                    biz_code=biz_code,
                )
            data = payload.get("data", payload)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # some responses wrap the collection: {data: {records|list: [...]}}
                for key in ("records", "list", "rows", "content"):
                    value = data.get(key)
                    if isinstance(value, list):
                        return value
                return data
            return {}
        return payload

    # ------------------------------------------------------------------
    # read APIs (never raise when Sonic is not configured)
    # ------------------------------------------------------------------
    def list_devices(self, project_id=None) -> list:
        """在线设备列表；未配置 Sonic 时返回 ``[]``。"""
        if not self.configured:
            return []
        params = {"projectId": project_id} if project_id else None
        try:
            response = self.request("get", "devices", params=params)
            data = self._payload(response)
        except SonicAPIError as exc:
            logger.warning("sonic list_devices failed: %s", exc)
            return []
        return _as_list(data)

    def get_device(self, udid) -> dict:
        """单设备详情；未配置 Sonic 时返回 ``{}``。"""
        if not self.configured:
            return {}
        try:
            response = self.request("get", "device", udid=udid)
            data = self._payload(response)
        except SonicAPIError as exc:
            logger.warning("sonic get_device(%s) failed: %s", udid, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def device_remote_info(self, udid) -> dict:
        """远控信息（ws 地址 + jmuxer 参数）；未配置 Sonic 时返回 ``{}``。"""
        if not self.configured:
            return {}
        response = self.request("get", "device_remote", udid=udid)
        data = self._payload(response)
        return build_remote_info(data if isinstance(data, dict) else {}, udid)

    def list_element_pages(self, project_id=None) -> list:
        """Sonic ElementPages 列表；未配置 Sonic 时返回 ``[]``。"""
        if not self.configured:
            return []
        params = {"projectId": project_id} if project_id else None
        try:
            response = self.request("get", "element_pages", params=params)
            data = self._payload(response)
        except SonicAPIError as exc:
            logger.warning("sonic list_element_pages failed: %s", exc)
            return []
        return _as_list(data)

    def list_test_suites(self, project_id=None) -> list:
        """Sonic 测试套件列表；未配置 Sonic 时返回 ``[]``。"""
        if not self.configured:
            return []
        params = {"projectId": project_id} if project_id else None
        try:
            response = self.request("get", "test_suites", params=params)
            data = self._payload(response)
        except SonicAPIError as exc:
            logger.warning("sonic list_test_suites failed: %s", exc)
            return []
        return _as_list(data)

    def list_projects(self) -> list:
        """Sonic 项目列表；未配置 Sonic 时返回 ``[]``。"""
        if not self.configured:
            return []
        try:
            response = self.request("get", "projects")
            data = self._payload(response)
        except SonicAPIError as exc:
            logger.warning("sonic list_projects failed: %s", exc)
            return []
        return _as_list(data)

    def suite_result(self, suite_id) -> dict:
        """套件执行结果；未配置 Sonic 时返回 ``{}``。"""
        if not self.configured:
            return {}
        response = self.request("get", "suite_result", suite_id=suite_id)
        data = self._payload(response)
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # write / action APIs (raise friendly BusinessError when not configured)
    # ------------------------------------------------------------------
    def run_suite(self, suite_id, device_udid=None, device_id=None,
                  project_id=None, payload=None) -> dict:
        """触发 Sonic 套件执行；未配置 Sonic 时抛 ``sonic_not_configured``。"""
        self._require_configured()
        body = dict(payload or {})
        body.setdefault("suiteId", suite_id)
        if project_id:
            body.setdefault("projectId", project_id)
        if device_udid:
            body.setdefault("udid", device_udid)
        if device_id:
            body.setdefault("deviceId", device_id)
        response = self.request("post", "run_suite", json=body)
        data = self._payload(response)
        return data if isinstance(data, dict) else {}


def _as_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "list", "rows", "content", "devices", "pages"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data] if data else []
    return []


def build_remote_info(data: dict, udid) -> dict:
    """Normalise Sonic remote debug payload into ``{ws_url, jmuxer}``."""
    data = data or {}
    ws_url = ""
    for key in ("wsUrl", "ws_url", "remoteUrl", "remote_url", "url", "remote"):
        value = data.get(key)
        if isinstance(value, str) and value:
            ws_url = value
            break
    if not ws_url and data.get("port"):
        host = data.get("host") or data.get("ip") or "127.0.0.1"
        ws_url = f"ws://{host}:{data['port']}"
    jmuxer = {
        "ws_url": ws_url,
        "udid": udid,
        "width": data.get("width") or data.get("screenWidth") or 0,
        "height": data.get("height") or data.get("screenHeight") or 0,
        "dpr": data.get("dpr") or data.get("pixelRatio") or 1,
        "fps": data.get("fps") or 30,
        "mode": data.get("mode") or "live",
    }
    return {
        "udid": udid,
        "ws_url": ws_url,
        "jmuxer": jmuxer,
        "raw": data,
    }


def get_sonic_client(project=None) -> SonicClient:
    """Return a client; ``project.sonic_project_id`` wins over settings default.

    The project id itself is not part of the client credentials but is exposed on
    the returned instance (``client.project_id``) so callers do not have to look
    it up again.
    """
    project_id = ""
    if project is not None:
        project_id = getattr(project, "sonic_project_id", "") or ""
    if not project_id:
        project_id = getattr(settings, "SONIC_PROJECT_ID", "") or ""
    client = SonicClient()
    client.project_id = project_id
    return client
