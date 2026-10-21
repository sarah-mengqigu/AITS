"""webui_testcase Agent：需求 → Web UI 测试用例（用例设计 + 用例评审两节点）。"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from apps.ai_core.services.agents.base import BaseAgent
from apps.ai_core.services.graph import END, get_stategraph

ALLOWED_ACTIONS = {
    "goto",
    "click",
    "fill",
    "input",
    "select",
    "hover",
    "wait",
    "expect",
    "assert",
    "scroll",
    "press",
    "upload",
    "js",
}
PRIORITIES = {"high", "medium", "low"}


class WebUITestCaseState(TypedDict, total=False):
    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    cases: list
    result: Any


def _split_requirement(requirement: str) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"[\n；;。，,、]+", requirement or "")
        if part.strip()
    ]
    return parts[:6]


def build_rule_cases(requirement: str, base_url: str) -> list[dict]:
    """Deterministic fallback cases derived from the natural language requirement."""
    url = base_url or "/"
    actions = _split_requirement(requirement) or ["打开目标页面"]
    main_steps = [{"action": "goto", "target": url, "value": "", "expect": "页面加载成功"}]
    for action in actions[:3]:
        main_steps.append(
            {
                "action": "click",
                "target": action,
                "value": "",
                "expect": f"{action} 执行成功",
            }
        )
    main_steps.append(
        {"action": "expect", "target": "页面关键元素", "value": "", "expect": "结果符合需求"}
    )
    return [
        {
            "name": "页面主流程验证",
            "priority": "high",
            "description": "覆盖需求主路径",
            "steps": main_steps,
        },
        {
            "name": "表单输入校验",
            "priority": "medium",
            "description": "校验表单必填与格式提示",
            "steps": [
                {"action": "goto", "target": url, "value": "", "expect": "页面加载成功"},
                {"action": "fill", "target": "输入框", "value": "demo", "expect": "输入成功"},
                {"action": "click", "target": "提交按钮", "value": "", "expect": "提交成功"},
                {
                    "action": "expect",
                    "target": "成功提示",
                    "value": "",
                    "expect": "展示提交成功提示",
                },
            ],
        },
        {
            "name": "异常场景提示",
            "priority": "low",
            "description": "校验错误处理",
            "steps": [
                {"action": "goto", "target": url, "value": "", "expect": "页面加载成功"},
                {
                    "action": "fill",
                    "target": "输入框",
                    "value": "",
                    "expect": "触发必填校验",
                },
                {
                    "action": "expect",
                    "target": "错误提示",
                    "value": "",
                    "expect": "展示可读错误信息",
                },
            ],
        },
    ]


def normalize_case(case: dict, index: int, base_url: str) -> dict:
    name = str(case.get("name") or f"用例{index + 1}")
    priority = case.get("priority") if case.get("priority") in PRIORITIES else "medium"
    normalized_steps = []
    for raw_step in case.get("steps") or []:
        if not isinstance(raw_step, dict):
            continue
        action = str(raw_step.get("action") or raw_step.get("type") or "click").lower()
        if action not in ALLOWED_ACTIONS:
            action = "click"
        target = raw_step.get("target") or raw_step.get("selector") or raw_step.get("url") or ""
        value = raw_step.get("value", "")
        expect = raw_step.get("expect") or raw_step.get("assertion") or ""
        normalized_steps.append(
            {
                "action": action,
                "target": str(target),
                "value": "" if value is None else str(value),
                "expect": str(expect),
            }
        )
    if not normalized_steps:
        normalized_steps = [
            {
                "action": "goto",
                "target": base_url or "/",
                "value": "",
                "expect": "页面加载成功",
            }
        ]
    if not any(step["action"] == "goto" for step in normalized_steps):
        normalized_steps.insert(
            0,
            {
                "action": "goto",
                "target": base_url or "/",
                "value": "",
                "expect": "页面加载成功",
            },
        )
    return {
        "name": name,
        "priority": priority,
        "description": str(case.get("description") or ""),
        "steps": normalized_steps,
    }


class WebUITestCaseAgent(BaseAgent):
    name = "webui_testcase"
    description = "根据 Web UI 需求设计可执行的 UI 测试用例，并通过评审节点做结构校验与优先级评估"
    stream_channel = "webui_test_generation"
    task_type = "webui_testcase"
    state_schema = WebUITestCaseState

    def retrieval_query(self, state) -> str:
        return (state.get("payload") or {}).get("requirement") or ""

    def build_graph(self):
        graph = get_stategraph(self.state_schema)
        graph.add_node("prepare", self._wrap("prepare", self._node_prepare))
        graph.add_node("design", self._wrap("design", self._node_design))
        graph.add_node("review", self._wrap("review", self._node_review))
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "design")
        graph.add_edge("design", "review")
        graph.add_edge("review", END)
        return graph.compile()

    def build_prompt(self, payload: dict) -> str:
        return (
            f"[agent:{self.name}]\n"
            "请把下面的 Web UI 需求拆解为测试用例，返回 JSON：\n"
            '{"cases": [{"name": "...", "priority": "high|medium|low",'
            ' "steps": [{"action": "goto|click|fill|expect", "target": "...",'
            ' "value": "", "expect": "..."}]}]}\n'
            f"需求：{payload.get('requirement') or ''}\n"
            f"站点地址：{payload.get('base_url') or ''}\n"
            "请仅输出 JSON。"
        )

    # ------------------------------------------------------------------
    # nodes
    # ------------------------------------------------------------------
    def _node_design(self, state) -> dict:
        payload = state.get("payload") or {}
        base_url = str(payload.get("base_url") or "")
        update = self.llm_generate(state)
        data = update.get("llm_data") or {}
        raw_cases = data.get("cases") if isinstance(data, dict) else None
        cases = [
            normalize_case(case, index, base_url)
            for index, case in enumerate(raw_cases or [])
            if isinstance(case, dict)
        ]
        if not cases:
            cases = [
                normalize_case(case, index, base_url)
                for index, case in enumerate(
                    build_rule_cases(str(payload.get("requirement") or ""), base_url)
                )
            ]
        return {
            "cases": cases,
            "llm_text": update.get("llm_text"),
            "llm_data": data,
            "usage": update.get("usage") or [],
        }

    def _node_review(self, state) -> dict:
        payload = state.get("payload") or {}
        base_url = str(payload.get("base_url") or "")
        cases = list(state.get("cases") or [])
        reviewed = []
        seen_names = set()
        for index, case in enumerate(cases):
            normalized = normalize_case(case, index, base_url)
            if normalized["name"] in seen_names:
                normalized["name"] = f"{normalized['name']}-{index + 1}"
            seen_names.add(normalized["name"])
            reviewed.append(normalized)
        if not reviewed:
            reviewed = [
                normalize_case(case, index, base_url)
                for index, case in enumerate(
                    build_rule_cases(str(payload.get("requirement") or ""), base_url)
                )
            ]
        return {
            "result": {
                "cases": reviewed,
                "summary": {
                    "total": len(reviewed),
                    "high": sum(1 for case in reviewed if case["priority"] == "high"),
                    "medium": sum(1 for case in reviewed if case["priority"] == "medium"),
                    "low": sum(1 for case in reviewed if case["priority"] == "low"),
                },
            }
        }
