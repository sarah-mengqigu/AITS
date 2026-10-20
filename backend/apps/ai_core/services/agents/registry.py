"""Agent 注册表：7 个 Agent 的唯一发现入口。"""

from __future__ import annotations

from apps.ai_core.services.agents.api_scenario_agent import APIScenarioAgent
from apps.ai_core.services.agents.api_testcase_agent import APITestCaseAgent
from apps.ai_core.services.agents.base import BaseAgent
from apps.ai_core.services.agents.midscene_agent import MidsceneAgent
from apps.ai_core.services.agents.midscene_script_agent import MidsceneScriptAgent
from apps.ai_core.services.agents.postman_script_translator import PostmanScriptTranslator
from apps.ai_core.services.agents.webui_playwright_agent import WebUIPlaywrightAgent
from apps.ai_core.services.agents.webui_testcase_agent import WebUITestCaseAgent
from apps.common.api.api_exception_handler import BusinessError

AGENTS: dict[str, type[BaseAgent]] = {
    APITestCaseAgent.name: APITestCaseAgent,
    APIScenarioAgent.name: APIScenarioAgent,
    PostmanScriptTranslator.name: PostmanScriptTranslator,
    WebUITestCaseAgent.name: WebUITestCaseAgent,
    WebUIPlaywrightAgent.name: WebUIPlaywrightAgent,
    MidsceneAgent.name: MidsceneAgent,
    MidsceneScriptAgent.name: MidsceneScriptAgent,
}


def get_agent(name: str) -> BaseAgent:
    """Return a fresh agent instance; unknown names raise a 404 BusinessError."""
    agent_class = AGENTS.get(str(name or ""))
    if agent_class is None:
        raise BusinessError(
            message=f"未知的 Agent: {name}",
            code="agent_not_found",
            status_code=404,
        )
    return agent_class()


def run_agent(name: str, payload: dict | None = None, stream_task_id=None) -> dict:
    """Convenience helper used by the HTTP layer and other modules.

    Returns the agent outcome ``{"status", "result", "usage", "steps", ...}``.
    For cross-module convenience the agent specific keys (``script`` /
    ``content`` / ``cases`` / ``scenario`` ...) are also exposed at the top
    level, so callers may read either ``outcome["result"]["script"]`` or
    ``outcome["script"]``.
    """
    outcome = get_agent(name).run(payload or {}, stream_task_id=stream_task_id)
    result = outcome.get("result")
    if outcome.get("status") == "success" and isinstance(result, dict):
        for key, value in result.items():
            outcome.setdefault(key, value)
    return outcome


def list_agents() -> list[dict]:
    return [
        {"name": agent_class.name, "description": agent_class.description}
        for agent_class in AGENTS.values()
    ]
