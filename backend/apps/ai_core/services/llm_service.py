"""LLM 调用薄客户端（其它模块的**唯一** LLM 入口）。

支持的两种模式：

* ``mock``：``provider=mock`` / ``settings.AI_MOCK_MODE=True`` / 没有可用配置。
  输出完全确定性（依据 prompt 中的关键词 / ``[agent:xxx]`` 标签），
  用于离线开发、CI 与演示。
* 真实 provider：OpenAI 兼容 ``POST {base_url}/chat/completions``，
  超时 ``settings.AI_REQUEST_TIMEOUT``，失败重试 1 次后抛
  ``BusinessError(code="llm_error")``。

每次调用（成功或失败）都会写 ``LLMUsageLog`` 并更新 Prometheus 指标。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from django.conf import settings

from apps.common.api.api_exception_handler import BusinessError
from apps.common.metrics import record_ai
from apps.ai_core.services.langchain_bridge import (
    CHAT_OPENAI_AVAILABLE,
    build_chat_model,
    invoke_chat_model,
)

logger = logging.getLogger(__name__)

PREVIEW_LIMIT = 500

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "azure": "",
    "mock": "",
}

PROVIDER_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "huggingface": "",
    "azure": "",
    "mock": "aits-mock",
}

_AGENT_TAG_RE = re.compile(r"\[agent:([a-z_]+)\]")


@dataclass
class LLMResult:
    """Normalised LLM reply shared by every provider."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: dict = field(default_factory=dict)
    provider: str = ""
    model: str = ""

    def __post_init__(self):
        if not self.total_tokens:
            self.total_tokens = int(self.prompt_tokens or 0) + int(self.completion_tokens or 0)

    @property
    def tokens(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


# ---------------------------------------------------------------------------
# deterministic mock outputs
# ---------------------------------------------------------------------------
MOCK_PLAYWRIGHT_SCRIPT = '''from playwright.sync_api import sync_playwright


def run(page):
    page.goto("https://example.com")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button").first.click()
    assert page.title() is not None


def test_case():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            run(page)
        finally:
            browser.close()


if __name__ == "__main__":
    test_case()
'''

MOCK_MIDSCENE_YAML = """target: https://example.com
url: https://example.com
tasks:
  - name: 打开页面
    flow:
      - ai: 打开 https://example.com
      - aiAssert: 页面成功加载并展示主要内容
  - name: 验证核心流程
    flow:
      - ai: 执行需求中描述的核心操作
      - aiAssert: 操作结果符合需求预期
"""

MOCK_MIDSCENE_SCRIPT_YAML = """target: https://example.com
tasks:
  - name: 维护脚本主流程
    flow:
      - ai: 打开目标页面
      - aiAssert: 页面标题非空
      - ai: 执行需求描述的操作
      - aiAssert: 断言结果可见
"""


def _mock_api_testcase_cases() -> list[dict]:
    return [
        {
            "name": "正常参数请求",
            "case_type": "endpoint",
            "test_type": "positive",
            "request": {"method": "GET", "path": "/", "headers": {}, "params": {}, "body": None},
            "assertions": [{"type": "status_code", "expected": 200}],
        },
        {
            "name": "缺失必填参数",
            "case_type": "endpoint",
            "test_type": "negative",
            "request": {"method": "GET", "path": "/", "headers": {}, "params": {}, "body": None},
            "assertions": [{"type": "status_code", "expected": 400}],
        },
        {
            "name": "边界值参数",
            "case_type": "endpoint",
            "test_type": "boundary",
            "request": {"method": "GET", "path": "/", "headers": {}, "params": {}, "body": None},
            "assertions": [{"type": "status_code", "expected": 400}],
        },
        {
            "name": "越权与注入攻击",
            "case_type": "endpoint",
            "test_type": "security",
            "request": {"method": "GET", "path": "/", "headers": {}, "params": {}, "body": None},
            "assertions": [{"type": "status_code", "expected": 401}],
        },
    ]


def _mock_webui_cases() -> list[dict]:
    return [
        {
            "name": "页面主流程验证",
            "priority": "high",
            "steps": [
                {"action": "goto", "target": "/", "value": "", "expect": "页面加载成功"},
                {"action": "click", "target": "主要操作入口", "value": "", "expect": "进入目标页面"},
                {"action": "expect", "target": "页面关键元素", "value": "", "expect": "元素可见"},
            ],
        },
        {
            "name": "表单输入校验",
            "priority": "medium",
            "steps": [
                {"action": "goto", "target": "/", "value": "", "expect": "页面加载成功"},
                {"action": "fill", "target": "输入框", "value": "demo", "expect": "输入成功"},
                {"action": "click", "target": "提交按钮", "value": "", "expect": "提交成功"},
            ],
        },
        {
            "name": "异常场景提示",
            "priority": "low",
            "steps": [
                {"action": "goto", "target": "/", "value": "", "expect": "页面加载成功"},
                {"action": "fill", "target": "输入框", "value": "", "expect": "触发校验"},
                {"action": "expect", "target": "错误提示", "value": "", "expect": "展示校验提示"},
            ],
        },
    ]


def _mock_agent_output(agent: str) -> str | None:
    if agent == "api_testcase":
        return json.dumps({"cases": _mock_api_testcase_cases()}, ensure_ascii=False)
    if agent == "api_scenario":
        return json.dumps(
            {
                "scenario": {
                    "name": "核心业务流程验证",
                    "description": "按需求串联接口完成端到端业务验证",
                    "steps": [],
                }
            },
            ensure_ascii=False,
        )
    if agent == "postman_translator":
        return json.dumps(
            {
                "validations": [
                    {
                        "expression": "response.status_code == 200",
                        "expected": 200,
                        "message": "状态码为 200",
                    }
                ],
                "extracts": [{"name": "token", "path": "data.token", "source": "body"}],
                "variables": {},
            },
            ensure_ascii=False,
        )
    if agent == "webui_testcase":
        return json.dumps({"cases": _mock_webui_cases()}, ensure_ascii=False)
    if agent == "webui_playwright":
        return json.dumps(
            {"script": MOCK_PLAYWRIGHT_SCRIPT, "language": "python"}, ensure_ascii=False
        )
    if agent == "midscene":
        return json.dumps(
            {"script_type": "yaml", "content": MOCK_MIDSCENE_YAML}, ensure_ascii=False
        )
    if agent == "midscene_script":
        return json.dumps(
            {
                "content": MOCK_MIDSCENE_SCRIPT_YAML,
                "actions": [
                    {"type": "ai", "instruction": "打开目标页面"},
                    {"type": "aiAssert", "instruction": "页面标题非空"},
                ],
            },
            ensure_ascii=False,
        )
    return None


def _mock_by_keyword(prompt: str) -> str:
    """Keyword driven deterministic payload (used when no agent tag is present)."""
    text = (prompt or "").lower()
    if "playwright" in text:
        return json.dumps({"script": MOCK_PLAYWRIGHT_SCRIPT, "language": "python"},
                          ensure_ascii=False)
    if "testcase" in text or "用例" in text:
        return json.dumps({"cases": _mock_api_testcase_cases()}, ensure_ascii=False)
    if "diagnosis" in text or "诊断" in text:
        return json.dumps(
            {
                "diagnosis": "接口错误率升高，主要集中在下单链路",
                "summary": "接口错误率升高，主要集中在下单链路",
                "root_cause": "下游库存服务响应变慢导致超时",
                "probable_causes": ["下游库存服务 RT 升高", "连接池不足"],
                "severity": "high",
                "impact": "下单成功率下降",
                "suggestions": ["检查库存服务 RT", "增加连接池上限", "补充熔断降级策略"],
                "recommendations": ["检查库存服务 RT", "增加连接池上限", "补充熔断降级策略"],
            },
            ensure_ascii=False,
        )
    if "scenario" in text or "场景" in text:
        return json.dumps(
            {"scenario": {"name": "核心业务流程验证", "description": "端到端串联验证",
                          "steps": []}},
            ensure_ascii=False,
        )
    if "postman" in text or "pm.test" in text:
        return _mock_agent_output("postman_translator")
    if "midscene" in text or "yaml" in text:
        return json.dumps({"script_type": "yaml", "content": MOCK_MIDSCENE_YAML},
                          ensure_ascii=False)
    return json.dumps(
        {"result": "mock_response", "summary": (prompt or "")[:120]}, ensure_ascii=False
    )


def mock_chat_content(messages: list[dict]) -> str:
    """Deterministic mock reply for a message list."""
    prompt = "\n".join(
        str(message.get("content") or "")
        for message in (messages or [])
        if isinstance(message, dict)
    )
    match = _AGENT_TAG_RE.search(prompt)
    if match:
        specialised = _mock_agent_output(match.group(1))
        if specialised is not None:
            return specialised
    return _mock_by_keyword(prompt)


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _normalize_messages(messages) -> list[dict]:
    normalized = []
    for message in messages or []:
        if isinstance(message, dict):
            normalized.append(
                {
                    "role": str(message.get("role") or "user"),
                    "content": str(message.get("content") or ""),
                }
            )
        else:  # be forgiving about plain strings
            normalized.append({"role": "user", "content": str(message)})
    return normalized


def _preview_messages(messages: list[dict]) -> str:
    parts = [f"{m['role']}: {m['content']}" for m in messages]
    return "\n".join(parts)[:PREVIEW_LIMIT]


class LLMService:
    """Stateless-ish LLM client bound to one ``LLMConfiguration`` (or mock)."""

    def __init__(self, config=None, project=None):
        self.config = config
        self.project = project if project is not None else getattr(config, "project", None)
        # Filled in by ``ModelManager.chat`` for usage accounting.
        self.agent_name = ""
        self.task_type = ""
        self.task_id = None

    # ------------------------------------------------------------------
    # capabilities
    # ------------------------------------------------------------------
    @property
    def is_mock(self) -> bool:
        if self.config is None:
            return True
        if not getattr(self.config, "is_active", True):
            return True
        if getattr(self.config, "provider", "mock") == "mock":
            return True
        return bool(getattr(settings, "AI_MOCK_MODE", False))

    @property
    def backend(self) -> str:
        """Which client to use: ``langchain`` when available, else ``http``."""
        configured = str(getattr(settings, "AITS_LLM_BACKEND", "auto") or "auto").lower()
        if configured == "http":
            return "http"
        return "langchain" if CHAT_OPENAI_AVAILABLE else "http"

    @property
    def provider_name(self) -> str:
        if self.is_mock:
            return "mock"
        return getattr(self.config, "provider", "") or "mock"

    @property
    def model_name(self) -> str:
        if self.config is None:
            return "aits-mock"
        configured = getattr(self.config, "model_name", "") or ""
        if self.is_mock and not configured:
            return "aits-mock"
        return configured or PROVIDER_DEFAULT_MODELS.get(self.provider_name, "")

    @property
    def temperature(self) -> float:
        return float(getattr(self.config, "temperature", 0.7) or 0.0)

    @property
    def max_tokens(self) -> int:
        return int(getattr(self.config, "max_tokens", 2048) or 2048)

    @property
    def base_url(self) -> str:
        configured = (getattr(self.config, "base_url", "") or "").strip()
        if configured:
            return configured.rstrip("/")
        return PROVIDER_BASE_URLS.get(self.provider_name, "").rstrip("/")

    @property
    def api_key(self) -> str:
        return (getattr(self.config, "api_key", "") or "").strip()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict],
        temperature=None,
        max_tokens=None,
        response_format=None,
    ) -> LLMResult:
        messages = _normalize_messages(messages)
        started = time.monotonic()
        try:
            if self.is_mock:
                result = self._mock_chat(messages)
            elif self.backend == "langchain":
                result = self._langchain_chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            else:
                result = self._remote_chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
        except BusinessError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            self._record_usage(None, elapsed, success=False, error_message=exc.message,
                               request_preview=_preview_messages(messages))
            raise
        except Exception as exc:  # pragma: no cover - defensive
            elapsed = int((time.monotonic() - started) * 1000)
            self._record_usage(None, elapsed, success=False, error_message=str(exc),
                               request_preview=_preview_messages(messages))
            raise BusinessError(
                message=f"LLM 调用失败: {exc}", code="llm_error", status_code=502
            ) from exc

        elapsed = int((time.monotonic() - started) * 1000)
        self._record_usage(result, elapsed, success=True,
                           request_preview=_preview_messages(messages))
        record_ai(
            result.provider,
            self.agent_name,
            "success",
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )
        return result

    def test_connection(self) -> dict:
        """Connectivity probe used by ``POST /llm-configs/{id}/test/``."""
        started = time.monotonic()
        payload = [
            {"role": "system", "content": "你是连通性探测助手，只回复 ok。"},
            {"role": "user", "content": "ping"},
        ]
        try:
            result = self.chat(payload, max_tokens=8)
        except BusinessError as exc:
            return {
                "success": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "mock": self.is_mock,
                "message": exc.message,
                "error_code": exc.biz_code,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        return {
            "success": True,
            "provider": result.provider,
            "model": result.model,
            "mock": self.is_mock,
            "message": "连通性正常" if not self.is_mock else "Mock 模式（离线确定性输出）",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    # ------------------------------------------------------------------
    # providers
    # ------------------------------------------------------------------
    def _mock_chat(self, messages: list[dict]) -> LLMResult:
        text = mock_chat_content(messages)
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in messages) or 1
        completion_tokens = estimate_tokens(text)
        return LLMResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            raw={"mock": True, "provider": "mock", "model": self.model_name},
            provider="mock",
            model=self.model_name,
        )

    def _langchain_chat(self, messages, temperature=None, max_tokens=None,
                        response_format=None) -> LLMResult:
        """Call the model through LangChain's ``ChatOpenAI``."""
        timeout = int(getattr(settings, "AI_REQUEST_TIMEOUT", 120) or 120)
        try:
            model = build_chat_model(
                self.config,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if response_format is not None:
                model = model.bind(response_format=response_format)
            data = invoke_chat_model(model, messages)
        except BusinessError:
            raise
        except Exception as exc:
            logger.warning("langchain chat failed: %s", exc)
            raise BusinessError(
                message=f"LLM 调用失败: {exc}", code="llm_error", status_code=502
            ) from exc
        return LLMResult(
            text=data.get("text") or "",
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
            raw=data.get("raw") or {},
            provider=self.provider_name,
            model=str(data.get("model") or self.model_name),
        )

    def _endpoint_url(self) -> str:
        base = self.base_url
        if not base:
            raise BusinessError(
                message=f"provider {self.provider_name} 未配置 base_url",
                code="llm_config_error",
            )
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _build_payload(self, messages, temperature=None, max_tokens=None,
                       response_format=None) -> dict:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        extra_payload = (getattr(self.config, "extra", None) or {}).get("payload")
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        return payload

    def _request_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            if self.provider_name == "azure":
                headers["api-key"] = self.api_key
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _remote_chat(self, messages, temperature=None, max_tokens=None,
                     response_format=None) -> LLMResult:
        url = self._endpoint_url()
        payload = self._build_payload(messages, temperature, max_tokens, response_format)
        timeout = int(getattr(settings, "AI_REQUEST_TIMEOUT", 120) or 120)
        last_error: Exception | None = None
        # one retry (2 attempts) as per the contract
        for _attempt in range(2):
            try:
                response = requests.post(
                    url, headers=self._request_headers(), json=payload, timeout=timeout
                )
                response.raise_for_status()
                data = response.json()
                return self._parse_remote_response(data)
            except Exception as exc:  # noqa: BLE001 - retried then wrapped
                last_error = exc
                logger.warning("llm request failed (%s): %s", url, exc)
        raise BusinessError(
            message=f"LLM 调用失败（已重试 1 次）: {last_error}",
            code="llm_error",
            status_code=502,
        )

    def _parse_remote_response(self, data: Any) -> LLMResult:
        if not isinstance(data, dict):
            raise BusinessError(message="LLM 返回结构非法", code="llm_error", status_code=502)
        choice = (data.get("choices") or [{}])[0] or {}
        content = (choice.get("message") or {}).get("content")
        if content is None:
            content = choice.get("text") or ""
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or prompt_tokens + completion_tokens
        )
        return LLMResult(
            text=str(content or ""),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw=data,
            provider=self.provider_name,
            model=str(data.get("model") or self.model_name),
        )

    # ------------------------------------------------------------------
    # accounting
    # ------------------------------------------------------------------
    def _record_usage(
        self,
        result: LLMResult | None,
        elapsed_ms: int,
        *,
        success: bool,
        error_message: str = "",
        request_preview: str = "",
    ) -> None:
        if not success:
            record_ai(self.provider_name, self.agent_name, "error")
        try:
            from apps.ai_core.models import LLMUsageLog

            LLMUsageLog.objects.create(
                project=self.project,
                config=self.config,
                agent_name=self.agent_name or "",
                task_type=self.task_type or "",
                task_id=str(self.task_id) if self.task_id else "",
                prompt_tokens=int(getattr(result, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(result, "completion_tokens", 0) or 0),
                total_tokens=int(getattr(result, "total_tokens", 0) or 0),
                response_time_ms=int(elapsed_ms or 0),
                success=success,
                error_message=(error_message or "")[:2000],
                request_preview=(request_preview or "")[:PREVIEW_LIMIT],
                response_preview=(getattr(result, "text", "") or "")[:PREVIEW_LIMIT],
            )
        except Exception as exc:  # pragma: no cover - logging must never break calls
            logger.warning("failed to persist LLMUsageLog: %s", exc)


def get_llm_service(config=None, project=None) -> LLMService:
    return LLMService(config=config, project=project)
