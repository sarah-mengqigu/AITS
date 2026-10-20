"""自然语言需求 -> App 用例步骤（ARCHITECTURE §2.5）.

调用链：
1. 惰性导入 ``apps.ai_core``（``ModelManager`` / ``LLMService``），仅在**真实 LLM
   配置可用**（``is_mock == False``）时才发请求；ai_core 缺失、异常、mock 模式或
   返回内容不可解析时全部降级到规则生成。
2. 规则生成是确定性的：按需求文本切分动作，输出 App 语义的步骤
   （``start_app/tap/input/swipe/assert/wait/back/stop_app``）。

因此本模块在无 LLM / 无网络环境中也总是可用且可断言。
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

#: 生成结果里允许的 App 动作（与 case_converter 保持一致）
ALLOWED_ACTIONS = {
    "tap", "click", "input", "fill", "swipe", "assert", "assert_text",
    "wait", "back", "start_app", "stop_app",
}

#: 关键词 -> 动作（规则生成用）
KEYWORD_ACTIONS = (
    ("启动", "start_app"),
    ("打开应用", "start_app"),
    ("打开", "tap"),
    ("点击", "tap"),
    ("单击", "tap"),
    ("输入", "input"),
    ("填写", "input"),
    ("搜索", "input"),
    ("滑动", "swipe"),
    ("上滑", "swipe"),
    ("下拉", "swipe"),
    ("返回", "back"),
    ("判断", "assert"),
    ("校验", "assert"),
    ("断言", "assert"),
    ("验证", "assert"),
    ("检查", "assert"),
    ("等待", "wait"),
    ("退出", "stop_app"),
    ("关闭", "stop_app"),
)

DEFAULT_APP = "应用"


def _split_requirement(requirement: str) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"[\n；;。，,、]+", requirement or "")
        if part.strip()
    ]
    return parts[:8]


def _action_for(text: str) -> str:
    for keyword, action in KEYWORD_ACTIONS:
        if keyword in text:
            return action
    return "tap"


def _target_for(text: str) -> str:
    cleaned = text
    for keyword, _ in KEYWORD_ACTIONS:
        if cleaned.startswith(keyword):
            cleaned = cleaned[len(keyword):]
            break
    cleaned = re.sub(r"^(在|于|到|并|然后|接着|再)+", "", cleaned)
    return cleaned.strip() or text


def _value_for(text: str, action: str) -> str:
    if action not in ("input", "fill"):
        return ""
    match = re.search(r"[\"“'‘]([^\"”'’]+)[\"”'’]", text)
    if match:
        return match.group(1)
    match = re.search(r"(?:输入|填写|搜索)([^\s，,。；;]+)", text)
    return match.group(1) if match else ""


def build_rule_steps(requirement: str, platform: str = "android") -> list[dict]:
    """Deterministic rule based step generation (no external dependency)."""
    platform = platform or "android"
    steps = [
        {
            "action": "start_app",
            "target": f"{DEFAULT_APP}（{platform}）",
            "value": "",
            "expect": "应用启动成功",
            "description": "启动被测应用",
        }
    ]
    parts = _split_requirement(requirement)
    for part in parts:
        action = _action_for(part)
        if action == "start_app":
            continue
        steps.append(
            {
                "action": action,
                "target": _target_for(part),
                "value": _value_for(part, action),
                "expect": f"{part}执行成功",
                "description": part,
            }
        )
    if not parts:
        steps.append(
            {
                "action": "assert",
                "target": "首页关键元素",
                "value": "",
                "expect": "首页展示正常",
                "description": "校验首页",
            }
        )
    steps.append(
        {
            "action": "assert",
            "target": "关键结果",
            "value": "",
            "expect": "结果符合需求",
            "description": "对比预期结果",
        }
    )
    steps.append(
        {
            "action": "stop_app",
            "target": f"{DEFAULT_APP}（{platform}）",
            "value": "",
            "expect": "应用退出成功",
            "description": "退出被测应用",
        }
    )
    return steps


# ---------------------------------------------------------------------------
# optional AI path
# ---------------------------------------------------------------------------
def _llm_steps(requirement: str, project=None, platform: str = "android"):
    """Try the ai_core LLM; returns ``None`` whenever unavailable/mock/failed."""
    try:
        from apps.ai_core.services.llm_service import LLMService
        from apps.ai_core.services.model_manager import get_model_manager

        manager = get_model_manager()
        config = manager.get_text_model(project)
        service = LLMService(config=config, project=project)
        if service.is_mock:
            # Deterministic mock output is not App specific -> use rules instead.
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    "你是移动端 App 自动化测试专家。根据需求输出 JSON："
                    '{"steps":[{"action":"start_app|tap|input|swipe|assert|'
                    'wait|back|stop_app","target":"...","value":"...",'
                    '"expect":"...","description":"..."}]}。只输出 JSON。'
                ),
            },
            {
                "role": "user",
                "content": f"平台: {platform}\n需求: {requirement}",
            },
        ]
        result = service.chat(messages, max_tokens=1200)
        return _parse_llm_steps(getattr(result, "text", "") or "")
    except Exception:  # noqa: BLE001 - ai_core is strictly optional
        logger.info("ai_core step generation unavailable, falling back to rules",
                    exc_info=True)
        return None


def _parse_llm_steps(text: str):
    """Parse ``{"steps": [...]}`` out of an LLM reply; ``None`` when invalid."""
    if not text:
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(raw[start:end + 1])
        except (TypeError, ValueError):
            return None
    steps = payload.get("steps") if isinstance(payload, dict) else payload
    if not isinstance(steps, list):
        return None
    cleaned = []
    for raw_step in steps:
        if not isinstance(raw_step, dict):
            continue
        action = str(raw_step.get("action") or "").lower()
        if action not in ALLOWED_ACTIONS:
            continue
        cleaned.append(
            {
                "action": action,
                "target": str(raw_step.get("target") or ""),
                "value": str(raw_step.get("value") or ""),
                "expect": str(raw_step.get("expect") or ""),
                "description": str(raw_step.get("description") or ""),
            }
        )
    return cleaned or None


def generate_steps(requirement: str, project=None, platform: str = "android") -> dict:
    """Generate AITS steps (+ Sonic snapshot) from a natural language requirement.

    Returns ``{"steps": [...], "sonic_steps": [...], "generated_by": "ai"|"rule",
    "requirement": str}``.
    """
    from apps.app_testing.services.case_converter import aits_steps_to_sonic

    requirement = (requirement or "").strip()
    steps = _llm_steps(requirement, project=project, platform=platform)
    generated_by = "ai"
    if not steps:
        steps = build_rule_steps(requirement, platform=platform)
        generated_by = "rule"
    return {
        "steps": steps,
        "sonic_steps": aits_steps_to_sonic(steps),
        "generated_by": generated_by,
        "requirement": requirement,
    }
