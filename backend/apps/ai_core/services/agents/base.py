"""Agent 基类：统一状态、图执行、WebSocket 流式推送、结构化输出与 token 计量。

设计要点
--------
* 默认图：``prepare -> retrieve -> generate -> finalize``，子类可覆写
  ``build_graph`` 增加多节点（评审 / 校验 / 修复等）流程。
* 每个节点执行前后通过 ``WebSocketMessageService.push_stream`` 推送
  ``node/start``、``chunk``、``node/end``；``stream_task_id`` 为空则跳过。
* 每次 LLM 调用经 ``ModelManager.chat`` → 自动写 ``LLMUsageLog``
  （agent_name / task_type / task_id）并更新 Prometheus 指标。
* ``run`` 永不把异常抛给调用方：返回 ``{"status": "error", "error": ...}``。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypedDict

from apps.ai_core.services.graph import END, get_stategraph
from apps.ai_core.services.model_manager import get_model_manager
from apps.ai_core.services.rag_service import RAGService
from apps.common.api.api_exception_handler import BusinessError
from apps.ai_core.services.langchain_bridge import (
    parse_json_output,
    render_messages,
)
from apps.common.websocket.core import WebSocketMessageService

logger = logging.getLogger(__name__)

CHUNK_PREVIEW_LIMIT = 400


class BaseAgentState(TypedDict, total=False):
    """Base state flowing through an agent graph."""

    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    result: Any
    validation: dict


class BaseAgent:
    """Common behaviour shared by the seven AIS agents."""

    name: str = ""
    description: str = ""
    state_schema: type = BaseAgentState
    stream_channel: str = "agent_generation"
    task_type: str = ""
    rag_top_k: int = 3
    system_prompt: str = "你是 AITS 智能测试平台的资深测试专家。只输出结构化 JSON，不要输出多余解释。"

    def __init__(self):
        self._stream_task_id: str | None = None
        self._steps: list[dict] = []
        self._usage: list[dict] = []

    # ------------------------------------------------------------------
    # graph construction
    # ------------------------------------------------------------------
    def build_graph(self):
        graph = get_stategraph(self.state_schema)
        graph.add_node("prepare", self._wrap("prepare", self._node_prepare))
        graph.add_node("retrieve", self._wrap("retrieve", self.rag_retrieve))
        graph.add_node("generate", self._wrap("generate", self.llm_generate))
        graph.add_node("finalize", self._wrap("finalize", self._node_finalize))
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _wrap(self, node_name: str, fn):
        """Decorate a node with step timing and WebSocket frames."""

        def wrapped(state):
            self._push(
                {
                    "type": "node/start",
                    "agent": self.name,
                    "node": node_name,
                    "status": "running",
                }
            )
            started = time.monotonic()
            try:
                update = fn(state) or {}
            except Exception:
                self._push(
                    {
                        "type": "node/end",
                        "agent": self.name,
                        "node": node_name,
                        "status": "error",
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                raise
            elapsed = int((time.monotonic() - started) * 1000)
            self._steps.append(
                {"node": node_name, "status": "success", "elapsed_ms": elapsed}
            )
            self._push(
                {
                    "type": "node/end",
                    "agent": self.name,
                    "node": node_name,
                    "status": "success",
                    "elapsed_ms": elapsed,
                }
            )
            return update

        return wrapped

    # ------------------------------------------------------------------
    # nodes
    # ------------------------------------------------------------------
    def _node_prepare(self, state) -> dict:
        payload = state.get("payload") or {}
        return {"prompt": self.build_prompt(payload)}

    def rag_retrieve(self, state) -> dict:
        """Retrieve RAG context; always degrades to an empty list."""
        query = self.retrieval_query(state)
        if not query or not str(query).strip():
            return {"retrieved": []}
        try:
            service = RAGService(project=state.get("project"))
            results = service.search(
                str(query), project=state.get("project"), top_k=self.rag_top_k
            )
        except Exception as exc:  # RAG is always optional
            logger.warning("rag retrieve failed for %s: %s", self.name, exc)
            results = []
        return {"retrieved": results}

    def llm_generate(self, state) -> dict:
        prompt = state.get("prompt") or self.build_prompt(state.get("payload") or {})
        messages = self.build_messages(prompt)
        result = get_model_manager().chat(
            messages,
            project=state.get("project"),
            agent_name=self.name,
            task_type=self.task_type or self.name,
            task_id=self._stream_task_id,
        )
        self._push(
            {
                "type": "chunk",
                "agent": self.name,
                "node": "generate",
                "chunk": (result.text or "")[:CHUNK_PREVIEW_LIMIT],
            }
        )
        entry = {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "provider": result.provider,
            "model": result.model,
        }
        self._usage.append(entry)
        return {
            "llm_text": result.text,
            "llm_data": parse_json_output(result.text),
            "usage": [entry],
        }

    def _node_finalize(self, state) -> dict:
        payload = state.get("payload") or {}
        result = self.compose_result(payload, state.get("llm_data"), state)
        if result is None:
            result = state.get("llm_data") or {"text": state.get("llm_text") or ""}
        if isinstance(result, str):
            parsed = parse_json_output(result)
            result = parsed if parsed is not None else {"text": result}
        return {"result": result}

    # ------------------------------------------------------------------
    # overridables
    # ------------------------------------------------------------------
    def build_prompt(self, payload: dict) -> str:
        return (
            f"[agent:{self.name}]\n"
            f"任务：{self.description}\n"
            f"输入：{json.dumps(payload, ensure_ascii=False, default=str)}\n"
            "请只返回 JSON。"
        )

    def build_messages(self, prompt: str) -> list[dict]:
        # LangChain ChatPromptTemplate when available, plain dicts otherwise.
        return render_messages(self.system_prompt, prompt)

    def retrieval_query(self, state) -> str:
        payload = state.get("payload") or {}
        return payload.get("requirement") or payload.get("query") or ""

    def compose_result(self, payload: dict, llm_data: Any, state: dict) -> Any:
        return llm_data if llm_data is not None else {"text": state.get("llm_text") or ""}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def validate_output(self, data, required=()) -> dict:
        """Raise ``BusinessError`` when a structured output is unusable."""
        if not isinstance(data, dict):
            raise BusinessError(
                message=f"{self.name} 输出不是 JSON 对象", code="invalid_llm_output"
            )
        missing = [key for key in required if data.get(key) in (None, "", [], {})]
        if missing:
            raise BusinessError(
                message=f"{self.name} 输出缺少字段: {', '.join(missing)}",
                code="invalid_llm_output",
            )
        return data

    def resolve_project(self, payload: dict):
        project = payload.get("project")
        if project is not None and not isinstance(project, (int, str)):
            return project
        project_id = payload.get("project_id")
        if project_id is None and isinstance(project, (int, str)) and str(project).isdigit():
            project_id = project
        if not project_id:
            return None
        try:
            from apps.projects.models import Project

            return Project.objects.filter(pk=project_id).first()
        except Exception:  # pragma: no cover - DB unavailable
            return None

    def initial_state(self, payload: dict) -> dict:
        return {
            "payload": payload,
            "project": self.resolve_project(payload),
            "retrieved": [],
            "usage": [],
        }

    def _push(self, payload: dict) -> None:
        if not self._stream_task_id:
            return
        try:
            WebSocketMessageService.push_stream(
                self.stream_channel, self._stream_task_id, payload
            )
        except Exception as exc:  # pragma: no cover - ws is best effort
            logger.warning("agent ws push failed: %s", exc)

    def _aggregate_usage(self) -> dict:
        prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in self._usage)
        completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in self._usage)
        providers = sorted({item.get("provider") or "" for item in self._usage})
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "calls": len(self._usage),
            "providers": [provider for provider in providers if provider],
        }

    # ------------------------------------------------------------------
    # entrypoint
    # ------------------------------------------------------------------
    def run(self, payload: dict | None = None, stream_task_id=None) -> dict:
        self._stream_task_id = str(stream_task_id) if stream_task_id else None
        self._steps = []
        self._usage = []
        started = time.monotonic()
        payload = dict(payload) if isinstance(payload, dict) else {"input": payload}
        try:
            graph = self.build_graph()
            final_state = graph.invoke(self.initial_state(payload))
            result = final_state.get("result")
            if result is None:
                result = self.compose_result(payload, final_state.get("llm_data"), final_state)
            if isinstance(result, str):
                parsed = extract_first_object(result)
                result = parsed if parsed is not None else {"text": result}
            return {
                "status": "success",
                "agent": self.name,
                "result": result,
                "usage": self._aggregate_usage(),
                "steps": list(self._steps),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        except BusinessError as exc:
            logger.warning("agent %s failed: %s", self.name, exc.message)
            return {
                "status": "error",
                "agent": self.name,
                "error": exc.message,
                "code": exc.biz_code,
                "usage": self._aggregate_usage(),
                "steps": list(self._steps),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("agent %s crashed", self.name)
            return {
                "status": "error",
                "agent": self.name,
                "error": str(exc),
                "code": "agent_error",
                "usage": self._aggregate_usage(),
                "steps": list(self._steps),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
