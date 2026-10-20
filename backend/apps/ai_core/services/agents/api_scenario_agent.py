"""api_scenario Agent：需求 + 端点列表 → 可执行的接口业务场景。

LangGraph 多节点：``intent -> map_endpoints -> build_steps -> validate``。
"""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from apps.ai_core.services.agents.base import BaseAgent
from apps.ai_core.services.graph import END
from apps.common.api.api_exception_handler import BusinessError

_PATH_VAR_RE = re.compile(r"\{([^{}]+)\}")


class APIScenarioState(TypedDict, total=False):
    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    intent: str
    intent_description: str
    mapped_endpoints: list
    steps: list
    result: Any


def _endpoint_list(payload: dict) -> list[dict]:
    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list):
        endpoint = payload.get("endpoint")
        endpoints = [endpoint] if isinstance(endpoint, dict) else []
    return [endpoint for endpoint in endpoints if isinstance(endpoint, dict)]


def _keywords(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[0-9A-Za-z_]+|[\u4e00-\u9fff]{1,4}", text or "")}


def _path_param_sample(path: str, parameters) -> dict:
    samples = {}
    for parameter in parameters or []:
        if isinstance(parameter, dict) and parameter.get("name") and parameter.get("in") in (None, "path"):
            samples[parameter["name"]] = parameter.get("example", "1")
    return samples


class APIScenarioAgent(BaseAgent):
    name = "api_scenario"
    description = "根据自然语言需求与接口列表生成端到端接口业务场景（含步骤、断言与提取）"
    stream_channel = "scenario_generation"
    task_type = "api_scenario"
    state_schema = APIScenarioState

    # ------------------------------------------------------------------
    # graph
    # ------------------------------------------------------------------
    def build_graph(self):
        from apps.ai_core.services.graph import StateGraph

        graph = StateGraph(self.state_schema)
        graph.add_node("prepare", self._wrap("prepare", self._node_prepare))
        graph.add_node("intent", self._wrap("intent", self._node_intent))
        graph.add_node(
            "map_endpoints", self._wrap("map_endpoints", self._node_map_endpoints)
        )
        graph.add_node("build_steps", self._wrap("build_steps", self._node_build_steps))
        graph.add_node("validate", self._wrap("validate", self._node_validate))
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "intent")
        graph.add_edge("intent", "map_endpoints")
        graph.add_edge("map_endpoints", "build_steps")
        graph.add_edge("build_steps", "validate")
        graph.add_edge("validate", END)
        return graph.compile()

    # ------------------------------------------------------------------
    # prompt
    # ------------------------------------------------------------------
    def retrieval_query(self, state) -> str:
        return (state.get("payload") or {}).get("requirement") or ""

    def build_prompt(self, payload: dict) -> str:
        return (
            f"[agent:{self.name}]\n"
            "请把业务需求拆解为接口测试场景，返回 JSON：\n"
            '{"scenario": {"name": "...", "description": "...", "steps": []}}\n'
            f"需求：{payload.get('requirement') or ''}\n"
            f"可用接口：{json.dumps(_endpoint_list(payload), ensure_ascii=False, default=str)}\n"
            "请仅输出 JSON。"
        )

    # ------------------------------------------------------------------
    # nodes
    # ------------------------------------------------------------------
    def _node_intent(self, state) -> dict:
        update = self.llm_generate(state)
        data = update.get("llm_data") or {}
        scenario = data.get("scenario") if isinstance(data, dict) else None
        requirement = (state.get("payload") or {}).get("requirement") or ""
        name = (scenario or {}).get("name") or self._rule_intent_name(requirement)
        description = (scenario or {}).get("description") or (
            f"依据需求「{requirement[:60]}」串联接口完成端到端验证"
        )
        return {
            "intent": str(name),
            "intent_description": str(description),
            "llm_text": update.get("llm_text"),
            "llm_data": data,
            "usage": update.get("usage") or [],
        }

    def _rule_intent_name(self, requirement: str) -> str:
        cleaned = (requirement or "").strip().replace("\n", " ")
        return f"{cleaned[:30]} 场景验证" if cleaned else "业务流程验证"

    def _node_map_endpoints(self, state) -> dict:
        payload = state.get("payload") or {}
        endpoints = _endpoint_list(payload)
        requirement = str(payload.get("requirement") or "")
        keywords = _keywords(requirement)
        scored = []
        for index, endpoint in enumerate(endpoints):
            text = " ".join(
                str(part)
                for part in (
                    endpoint.get("summary"),
                    endpoint.get("path"),
                    endpoint.get("operation_id"),
                    endpoint.get("description"),
                )
                if part
            )
            overlap = len(keywords & _keywords(text))
            scored.append((overlap, -index, endpoint))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        matched = [endpoint for overlap, _, endpoint in scored if overlap > 0]
        mapped = matched or [endpoint for _, _, endpoint in scored]
        return {"mapped_endpoints": mapped[:8]}

    def _node_build_steps(self, state) -> dict:
        mapped = state.get("mapped_endpoints") or []
        steps = []
        for index, endpoint in enumerate(mapped):
            method = str(endpoint.get("method") or "GET").upper()
            path = endpoint.get("path") or endpoint.get("url") or "/"
            samples = _path_param_sample(path, endpoint.get("parameters"))
            resolved_path = _PATH_VAR_RE.sub(
                lambda match: str(samples.get(match.group(1), "1")), str(path)
            )
            extract = {}
            if "id" in str(resolved_path).lower() or index < len(mapped) - 1:
                extract = {"id": "body.id"}
            steps.append(
                {
                    "name": str(endpoint.get("summary") or f"{method} {path}"),
                    "request": {
                        "method": method,
                        "path": resolved_path,
                        "params": {},
                        "headers": {"Content-Type": "application/json"},
                        "body": endpoint.get("request_body")
                        if isinstance(endpoint.get("request_body"), dict)
                        else None,
                    },
                    "assertions": [
                        {"type": "status_code", "operator": "in", "expected": [200, 201]},
                    ],
                    "extract": extract,
                }
            )
        if not steps:
            requirement = (state.get("payload") or {}).get("requirement") or "业务主流程"
            steps = [
                {
                    "name": "业务主流程",
                    "request": {"method": "GET", "path": "/", "params": {}, "headers": {}},
                    "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
                    "extract": {},
                    "description": str(requirement)[:120],
                }
            ]
        return {"steps": steps}

    def _node_validate(self, state) -> dict:
        steps = state.get("steps") or []
        if not steps:
            raise BusinessError(
                message="场景生成失败：没有可用步骤", code="invalid_agent_output"
            )
        normalized = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            request = step.get("request") if isinstance(step.get("request"), dict) else {}
            normalized.append(
                {
                    "name": str(step.get("name") or f"步骤{index + 1}"),
                    "request": {
                        "method": str(request.get("method") or "GET").upper(),
                        "path": request.get("path") or request.get("url") or "/",
                        "params": request.get("params") or {},
                        "headers": request.get("headers") or {},
                        "body": request.get("body"),
                    },
                    "assertions": step.get("assertions")
                    if isinstance(step.get("assertions"), list)
                    else [{"type": "status_code", "expected": 200}],
                    "extract": step.get("extract")
                    if isinstance(step.get("extract"), dict)
                    else {},
                }
            )
        if not normalized:
            raise BusinessError(
                message="场景生成失败：步骤结构非法", code="invalid_agent_output"
            )
        scenario = {
            "name": state.get("intent") or "业务流程验证",
            "description": state.get("intent_description") or "",
            "steps": normalized,
        }
        return {
            "result": {
                "scenario": scenario,
                "endpoint_count": len(
                    {step["request"]["path"] for step in normalized}
                ),
            }
        }
