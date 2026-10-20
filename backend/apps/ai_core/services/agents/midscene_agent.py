"""midscene Agent：需求 + 站点地址 → MidScene YAML 脚本（target/url/tasks/ai/aiAssert）。"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from apps.ai_core.services.agents.base import BaseAgent
from apps.common.api.api_exception_handler import BusinessError
from apps.common.parsers.yaml_json import dumps_yaml, parse_yaml

MIDSCENE_FLOW_KEYS = {
    "ai",
    "aiAssert",
    "aiAction",
    "aiQuery",
    "aiWaitFor",
    "aiInput",
    "aiTap",
    "aiScroll",
    "aiKeyboardPress",
}


class MidsceneState(TypedDict, total=False):
    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    result: Any


def build_midscene_document(payload: dict) -> dict:
    """Deterministic MidScene YAML document derived from requirement / steps."""
    payload = payload or {}
    url = str(payload.get("url") or payload.get("base_url") or "https://example.com")
    requirement = str(payload.get("requirement") or "").strip()
    steps = [step for step in (payload.get("steps") or []) if isinstance(step, dict)]
    tasks = []
    if steps:
        for index, step in enumerate(steps):
            instruction = str(
                step.get("instruction")
                or step.get("action")
                or step.get("name")
                or f"执行步骤{index + 1}"
            )
            expect = str(step.get("expect") or step.get("assertion") or "操作成功")
            tasks.append(
                {
                    "name": str(step.get("name") or f"步骤{index + 1}"),
                    "flow": [{"ai": instruction}, {"aiAssert": expect}],
                }
            )
    else:
        tasks = [
            {
                "name": "打开页面",
                "flow": [
                    {"ai": f"打开 {url}"},
                    {"aiAssert": "页面成功加载并展示主要内容"},
                ],
            },
            {
                "name": "验证需求",
                "flow": [
                    {"ai": requirement or "执行需求描述的核心操作"},
                    {
                        "aiAssert": f"{requirement[:40] or '操作结果'} 符合需求预期",
                    },
                ],
            },
        ]
    return {"target": url, "url": url, "tasks": tasks}


def validate_midscene_content(content: str) -> tuple[bool, list[str], dict | None]:
    """Validate a MidScene YAML string; returns ``(valid, issues, document)``."""
    if not str(content or "").strip():
        return False, ["内容为空"], None
    try:
        document = parse_yaml(content)
    except BusinessError as exc:
        return False, [exc.message], None
    if not isinstance(document, dict):
        return False, ["MidScene YAML 根节点必须是对象"], None
    issues: list[str] = []
    if not document.get("target") and not document.get("url"):
        issues.append("缺少 target 或 url")
    tasks = document.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        issues.append("tasks 必须为非空数组")
    else:
        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                issues.append(f"tasks[{index}] 必须是对象")
                continue
            flow = task.get("flow")
            if not isinstance(flow, list) or not flow:
                issues.append(f"tasks[{index}].flow 必须为非空数组")
                continue
            for position, item in enumerate(flow):
                if not isinstance(item, dict) or not (set(item.keys()) & MIDSCENE_FLOW_KEYS):
                    issues.append(
                        f"tasks[{index}].flow[{position}] 缺少 ai/aiAssert 指令"
                    )
    return (not issues), issues, document


def actions_from_document(document: dict) -> list[dict]:
    actions: list[dict] = []
    for task in (document or {}).get("tasks") or []:
        if not isinstance(task, dict):
            continue
        for item in task.get("flow") or []:
            if not isinstance(item, dict):
                continue
            for key in MIDSCENE_FLOW_KEYS:
                if key in item:
                    actions.append(
                        {
                            "type": key,
                            "instruction": str(item.get(key) or ""),
                            "task": str(task.get("name") or ""),
                        }
                    )
                    break
    return actions


class MidsceneAgent(BaseAgent):
    name = "midscene"
    description = "根据需求与站点地址生成 MidScene YAML 脚本（target/url/tasks/ai/aiAssert）"
    stream_channel = "midscene_script_generation"
    task_type = "midscene"
    state_schema = MidsceneState

    def retrieval_query(self, state) -> str:
        return (state.get("payload") or {}).get("requirement") or ""

    def build_prompt(self, payload: dict) -> str:
        return (
            f"[agent:{self.name}]\n"
            "请生成 MidScene YAML 脚本，包含 target、url、tasks（每个 task 有 flow，"
            "flow 内使用 ai / aiAssert 指令）。\n"
            f"需求：{payload.get('requirement') or ''}\n"
            f"站点地址：{payload.get('url') or payload.get('base_url') or ''}\n"
            '仅返回 JSON：{"script_type": "yaml", "content": "<yaml>"}'
        )

    def compose_result(self, payload: dict, llm_data, state) -> dict:
        url = str(payload.get("url") or payload.get("base_url") or "").strip()
        document = None
        if isinstance(llm_data, dict):
            content = llm_data.get("content") or llm_data.get("script")
            if content:
                valid, _issues, candidate = validate_midscene_content(str(content))
                if valid:
                    document = candidate
        if document is None:
            document = build_midscene_document(payload)
        if url:
            document["target"] = url
            document["url"] = url
        document.setdefault("url", document.get("target") or "https://example.com")
        content = dumps_yaml(document)
        valid, issues, _ = validate_midscene_content(content)
        if not valid:
            raise BusinessError(
                message=f"MidScene 脚本生成失败: {'; '.join(issues)}",
                code="invalid_agent_output",
            )
        return {
            "script_type": "yaml",
            "content": content,
            "target": document.get("target"),
            "tasks": len(document.get("tasks") or []),
            "valid": True,
        }
