"""midscene_script Agent：MidScene 脚本维护（生成 → 校验 → 修复）。

与 ``midscene`` 的区别：这里聚焦脚本的**可维护性**——先生成/接收草稿，
再用确定性规则校验结构，失败时自动进入修复节点重建，最终输出
``{content, actions}``。
"""

from __future__ import annotations

from typing import Any, TypedDict

from apps.ai_core.services.agents.base import BaseAgent
from apps.ai_core.services.agents.midscene_agent import (
    actions_from_document,
    build_midscene_document,
    validate_midscene_content,
)
from apps.ai_core.services.graph import END, StateGraph
from apps.common.parsers.yaml_json import dumps_yaml, parse_yaml


class MidsceneScriptState(TypedDict, total=False):
    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    content: str
    valid: bool
    issues: list
    repaired: bool
    result: Any


class MidsceneScriptAgent(BaseAgent):
    name = "midscene_script"
    description = "生成、校验并自动修复 MidScene YAML 脚本，输出可直接运行的脚本内容与动作清单"
    stream_channel = "midscene_script_generation"
    task_type = "midscene_script"
    state_schema = MidsceneScriptState

    def retrieval_query(self, state) -> str:
        payload = state.get("payload") or {}
        return payload.get("requirement") or ""

    # ------------------------------------------------------------------
    # graph: prepare -> generate -> validate -> (repair -> validate)* -> END
    # ------------------------------------------------------------------
    def build_graph(self):
        graph = StateGraph(self.state_schema)
        graph.add_node("prepare", self._wrap("prepare", self._node_prepare))
        graph.add_node("generate", self._wrap("generate", self._node_generate))
        graph.add_node("validate", self._wrap("validate", self._node_validate))
        graph.add_node("repair", self._wrap("repair", self._node_repair))
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {"repair": "repair", "end": END},
        )
        graph.add_edge("repair", "validate")
        return graph.compile()

    def _route_after_validate(self, state) -> str:
        return "end" if state.get("valid") else "repair"

    # ------------------------------------------------------------------
    def build_prompt(self, payload: dict) -> str:
        return (
            f"[agent:{self.name}]\n"
            "请生成或维护 MidScene YAML 脚本，返回 JSON：\n"
            '{"content": "<yaml with target/tasks/ai/aiAssert>",'
            ' "actions": [{"type": "ai", "instruction": "..."}]}\n'
            f"需求：{payload.get('requirement') or ''}\n"
            f"步骤：{payload.get('steps') or []}\n"
            f"站点地址：{payload.get('url') or payload.get('base_url') or ''}\n"
            "请仅输出 JSON。"
        )

    # ------------------------------------------------------------------
    # nodes
    # ------------------------------------------------------------------
    def _node_generate(self, state) -> dict:
        payload = state.get("payload") or {}
        update = self.llm_generate(state)
        data = update.get("llm_data") or {}
        content = None
        if isinstance(data, dict):
            raw = data.get("content") or data.get("script")
            if raw:
                content = str(raw)
        url = str(payload.get("url") or payload.get("base_url") or "").strip()
        if content:
            valid, _issues, document = validate_midscene_content(content)
            if valid and isinstance(document, dict):
                if url:
                    document["target"] = url
                    document["url"] = url
                content = dumps_yaml(document)
            else:
                content = None
        if not content:
            content = dumps_yaml(build_midscene_document(payload))
        return {
            "content": content,
            "valid": False,
            "issues": [],
            "repaired": False,
            "llm_text": update.get("llm_text"),
            "llm_data": data,
            "usage": update.get("usage") or [],
        }

    def _node_validate(self, state) -> dict:
        content = state.get("content") or ""
        valid, issues, document = validate_midscene_content(content)
        update: dict = {"valid": valid, "issues": issues}
        if valid:
            update["result"] = {
                "content": content,
                "script_type": "yaml",
                "actions": actions_from_document(document or {}),
                "repaired": bool(state.get("repaired")),
                "valid": True,
            }
        return update

    def _node_repair(self, state) -> dict:
        payload = state.get("payload") or {}
        repaired = build_midscene_document(payload)
        url = str(payload.get("url") or payload.get("base_url") or "").strip()
        if url:
            repaired["target"] = url
            repaired["url"] = url
        content = dumps_yaml(repaired)
        # belt and braces: parse the rebuilt content so the next validate passes
        try:
            parse_yaml(content)
        except Exception:  # pragma: no cover - deterministic dump should always parse
            content = dumps_yaml(build_midscene_document({}))
        return {"content": content, "valid": False, "repaired": True}
