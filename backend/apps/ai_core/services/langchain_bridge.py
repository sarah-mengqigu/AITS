"""LangChain 接入层（可选增强）。

本项目把 LangChain 用作**胶水层的可选实现**，所有能力都遵循同一模式：

1. 依赖可用 → 走 LangChain 官方抽象（ChatOpenAI / ChatPromptTemplate /
   JsonOutputParser / Embeddings / InMemoryVectorStore / StructuredTool /
   BaseCallbackHandler）；
2. 依赖缺失或调用异常 → 回退到项目内的等价实现，保证离线、Mock、无 Key
   环境照常运行。

这里只做“适配”，不改变业务语义：``LLMResult``、``RAGService`` 的返回结构、
Agent 的状态与节点都不变。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.common.api.api_exception_handler import BusinessError
from apps.common.parsers.yaml_json import extract_first_object

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# optional imports (each capability degrades independently)
# ---------------------------------------------------------------------------
try:  # core abstractions: prompts / parsers / messages / tools / documents
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.tools import StructuredTool

    LANGCHAIN_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on optional dependency
    LANGCHAIN_AVAILABLE = False
    BaseCallbackHandler = object  # type: ignore[assignment,misc]
    logger.debug("langchain_core unavailable: %s", exc)

def _spec_available(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # pragma: no cover - broken installation
        return False


# Heavy modules are imported lazily (at first real use) so booting the backend
# and running the mock-based test suite never pays for the OpenAI SDK, numpy or
# the in-memory vector store. Measured: langchain_openai ~+54 MB RSS,
# InMemoryVectorStore ~+38 MB; langchain_core itself is only ~+12 MB.
CHAT_OPENAI_AVAILABLE = LANGCHAIN_AVAILABLE and _spec_available("langchain_openai")
DEEPSEEK_AVAILABLE = LANGCHAIN_AVAILABLE and _spec_available("langchain_deepseek")
VECTORSTORE_AVAILABLE = (
    LANGCHAIN_AVAILABLE
    and _spec_available("langchain_core.vectorstores")
    and _spec_available("numpy")
)
LANGCHAIN_CHROMA_AVAILABLE = LANGCHAIN_AVAILABLE and _spec_available("langchain_chroma")

DEFAULT_SYSTEM_PROMPT = "你是 AITS 智能测试平台的资深测试专家。"


# ---------------------------------------------------------------------------
# messages & prompts
# ---------------------------------------------------------------------------
def to_lc_messages(messages: list[dict]):
    """Convert ``[{"role", "content"}]`` to LangChain message objects."""
    if not LANGCHAIN_AVAILABLE:
        return list(messages)
    mapping = {"system": SystemMessage, "assistant": AIMessage, "ai": AIMessage,
               "human": HumanMessage, "user": HumanMessage}
    converted = []
    for message in messages or []:
        role = str(message.get("role") or "user").lower()
        cls = mapping.get(role, HumanMessage)
        converted.append(cls(content=str(message.get("content") or "")))
    return converted


def render_messages(system_prompt: str, user_prompt: str) -> list[dict]:
    """Render a system+human prompt through ``ChatPromptTemplate``.

    Falls back to plain dicts when LangChain is unavailable, so the mock/HTTP
    paths keep receiving the exact same structure as before.
    """
    if not LANGCHAIN_AVAILABLE:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    try:
        template = ChatPromptTemplate.from_messages(
            [("system", "{system_prompt}"), ("human", "{user_prompt}")]
        )
        rendered = template.format_messages(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        return [
            {
                "role": "system" if isinstance(item, SystemMessage) else "user",
                "content": str(item.content),
            }
            for item in rendered
        ]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("ChatPromptTemplate render failed, using plain messages: %s", exc)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]


# ---------------------------------------------------------------------------
# structured output
# ---------------------------------------------------------------------------
def parse_json_output(text: str):
    """Parse LLM JSON through ``JsonOutputParser`` with a tolerant fallback.

    LLMs often wrap JSON in prose or code fences; the parser is tried first and
    :func:`extract_first_object` is used as a safety net. Returns ``None`` when
    no JSON object can be recovered.
    """
    if not text or not str(text).strip():
        return None
    if LANGCHAIN_AVAILABLE:
        try:
            return JsonOutputParser().parse(str(text))
        except Exception:
            pass
    return extract_first_object(str(text))


# ---------------------------------------------------------------------------
# chat models
# ---------------------------------------------------------------------------
class UsageTrackingHandler(BaseCallbackHandler):
    """LangChain callback that captures token usage for ``LLMUsageLog``."""

    def __init__(self):
        self.usage: dict[str, int] = {}
        self.model_name: str = ""

    def on_llm_end(self, response, **kwargs):  # noqa: D401 - LangChain callback
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            if isinstance(llm_output, dict):
                self.model_name = str(llm_output.get("model_name") or "")
                usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
                if isinstance(usage, dict) and usage:
                    self.usage = {
                        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                        "completion_tokens": int(usage.get("completion_tokens") or 0),
                        "total_tokens": int(usage.get("total_tokens") or 0),
                    }
                    return
            generations = getattr(response, "generations", None) or []
            if generations and generations[0]:
                message = getattr(generations[0][0], "message", None)
                metadata = getattr(message, "usage_metadata", None) or {}
                if metadata:
                    self.usage = {
                        "prompt_tokens": int(metadata.get("input_tokens") or 0),
                        "completion_tokens": int(metadata.get("output_tokens") or 0),
                        "total_tokens": int(metadata.get("total_tokens") or 0),
                    }
        except Exception as exc:  # pragma: no cover - callbacks must not break
            logger.debug("usage callback failed: %s", exc)


def build_chat_model(config, *, temperature=None, max_tokens=None,
                     timeout: int | None = None, base_url: str | None = None):
    """Build the right LangChain chat model for an ``LLMConfiguration``.

    Provider routing:

    * ``deepseek`` → ``langchain_deepseek.ChatDeepSeek`` (falls back to the
      OpenAI-compatible client when the package is absent);
    * everything else (OpenAI / Qwen / local HF / Azure / custom) →
      ``langchain_openai.ChatOpenAI`` with ``base_url`` + provider headers.
    """
    provider = str(getattr(config, "provider", "") or "openai").lower()
    model = str(getattr(config, "model_name", "") or "")
    resolved_base_url = str(
        base_url or getattr(config, "base_url", "") or ""
    ).rstrip("/")
    api_key = str(getattr(config, "api_key", "") or "").strip()
    resolved_temperature = float(
        getattr(config, "temperature", 0.7) if temperature is None else temperature
    )
    resolved_max_tokens = int(
        getattr(config, "max_tokens", 2048) if max_tokens is None else max_tokens
    )

    # --- DeepSeek: dedicated LangChain integration --------------------
    if provider == "deepseek" and DEEPSEEK_AVAILABLE:
        from langchain_deepseek import ChatDeepSeek  # lazy import

        deepseek_kwargs: dict[str, Any] = {
            "model": model or "deepseek-chat",
            "temperature": resolved_temperature,
            "max_tokens": resolved_max_tokens,
            "max_retries": 1,
        }
        if api_key:
            deepseek_kwargs["api_key"] = api_key
        if resolved_base_url:
            deepseek_kwargs["api_base"] = resolved_base_url
        if timeout:
            deepseek_kwargs["timeout"] = timeout
        return ChatDeepSeek(**deepseek_kwargs)

    if not CHAT_OPENAI_AVAILABLE:
        raise BusinessError(
            message="未安装 langchain-openai，无法使用 LangChain 模型客户端",
            code="langchain_unavailable",
        )
    from langchain_openai import ChatOpenAI  # lazy: heavy import (openai SDK)

    headers = {}
    if provider == "azure" and api_key:
        headers["api-key"] = api_key
        api_key = "azure"
    kwargs: dict[str, Any] = {
        "model": model or "gpt-4o-mini",
        "temperature": resolved_temperature,
        "max_tokens": resolved_max_tokens,
        "max_retries": 1,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url
    if headers:
        kwargs["default_headers"] = headers
    if timeout:
        kwargs["timeout"] = timeout
    return ChatOpenAI(**kwargs)


def invoke_chat_model(model, messages: list[dict]) -> dict:
    """Invoke a LangChain chat model and normalise the response."""
    handler = UsageTrackingHandler()
    response = model.invoke(to_lc_messages(messages), config={"callbacks": [handler]})
    text = ""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    metadata = getattr(response, "usage_metadata", None) or {}
    usage = handler.usage or {
        "prompt_tokens": int(metadata.get("input_tokens") or 0),
        "completion_tokens": int(metadata.get("output_tokens") or 0),
        "total_tokens": int(metadata.get("total_tokens") or 0),
    }
    return {
        "text": text,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(
            usage.get("total_tokens")
            or int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        ),
        "model": handler.model_name or getattr(response, "response_metadata", {}).get(
            "model_name", ""
        ),
        "raw": getattr(response, "response_metadata", {}) or {},
    }


# ---------------------------------------------------------------------------
# embeddings & vector store
# ---------------------------------------------------------------------------
def _embed_text(text: str, dim: int | None = None) -> list[float]:
    # Imported lazily to avoid a circular import with RAGService.
    from apps.ai_core.services.rag_service import EMBED_DIM, embed_text

    return embed_text(text, dim or EMBED_DIM)


if LANGCHAIN_AVAILABLE:

    class DeterministicEmbeddings(Embeddings):
        """LangChain ``Embeddings`` backed by the project's deterministic hashing.

        Keeps RAG fully offline (no model download) while still speaking the
        standard LangChain interface, so swapping in ``HuggingFaceEmbeddings``
        is a one-line change.
        """

        def embed_documents(self, texts):
            return [_embed_text(text) for text in texts]

        def embed_query(self, text):
            return _embed_text(text)


def build_vector_store(entries: list[dict]):
    """Build an ``InMemoryVectorStore`` from persisted chunk entries.

    ``entries``: ``[{"text", "document_id", "source"}]``. Returns ``None`` when
    the vector store extra (numpy) is unavailable — callers then use the
    built-in cosine search.
    """
    if not VECTORSTORE_AVAILABLE or not LANGCHAIN_AVAILABLE or not entries:
        return None
    try:
        from langchain_core.vectorstores import InMemoryVectorStore  # lazy: pulls numpy

        store = InMemoryVectorStore(embedding=DeterministicEmbeddings())
        documents = [
            Document(
                page_content=str(entry.get("text") or ""),
                metadata={
                    "document_id": int(entry.get("document_id") or 0),
                    "source": str(entry.get("source") or ""),
                },
            )
            for entry in entries
        ]
        store.add_documents(documents)
        return store
    except Exception as exc:  # pragma: no cover - optional backend
        logger.warning("build_vector_store failed, falling back to cosine: %s", exc)
        return None


# ---------------------------------------------------------------------------
# tools (MCP)
# ---------------------------------------------------------------------------
def build_mcp_tools(config) -> list:
    """Expose MCP tool definitions as LangChain ``StructuredTool`` objects.

    The tool *schema* is bindable to an LLM; execution requires a real MCP
    runtime, so calling the tool raises a clear ``BusinessError`` until a
    transport is configured.
    """
    if not LANGCHAIN_AVAILABLE:
        return []
    tools = []
    for spec in getattr(config, "discover_tools", lambda: [])():
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        description = str(spec.get("description") or name)
        schema = spec.get("input_schema") or {}

        def _not_available(payload: str = "", _name: str = name) -> str:
            raise BusinessError(
                message=f"MCP 工具 {_name} 需要真实 MCP 运行时（当前为离线工具索引）",
                code="mcp_runtime_unavailable",
            )

        try:
            tools.append(
                StructuredTool.from_function(
                    func=_not_available,
                    name=name,
                    description=f"{description}\n参数 schema: {schema}",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("cannot build tool %s: %s", name, exc)
    return tools


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------
def langchain_status() -> dict:
    """Capability probe used by docs / diagnostics endpoints."""
    return {
        "langchain_core": LANGCHAIN_AVAILABLE,
        "chat_openai": CHAT_OPENAI_AVAILABLE,
        "vectorstore": VECTORSTORE_AVAILABLE,
        "chroma": LANGCHAIN_CHROMA_AVAILABLE,
    }
