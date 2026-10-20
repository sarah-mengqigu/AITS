"""Natural language -> structured Web UI test steps / cases.

The AI bridge is lazy and optional: when ``apps.ai_core`` is unavailable (or a
call fails) a deterministic rule based parser produces usable steps, so the
endpoint and its tests never depend on a working LLM.
"""

from __future__ import annotations

import json
import logging
import re

from apps.web_testing.models import WebUITestCase

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s，,。;；）)\]]+")
QUOTED_RE = re.compile(r"[\"“”'‘’「」]([^\"“”'‘’「」]{1,120})[\"“”'‘’「」]")
DURATION_RE = re.compile(r"(\d+)\s*(毫秒|ms|秒|s)")
SPLIT_RE = re.compile(r"[\n;；。]+|(?:\d+[.、)])|(?:^-)", re.M)

KW_GOTO = ("打开", "访问", "进入", "跳转", "导航", "open", "visit", "goto", "navigate")
KW_CLICK = ("点击", "单击", "点一下", "点", "click", "tap", "press the")
KW_FILL = ("输入", "填写", "填入", "键入", "type", "fill", "input")
KW_ASSERT = ("断言", "验证", "检查", "确认", "应该", "看到", "显示", "包含", "assert",
             "expect", "verify", "should", "check")
KW_WAIT = ("等待", "稍等", "wait", "sleep", "pause")
KW_SELECT = ("选择", "下拉", "select", "choose")
KW_HOVER = ("悬停", "鼠标移", "hover")
KW_PRESS = ("按下", "回车", "enter", "press key", "keyboard")
KW_SCREENSHOT = ("截图", "screenshot", "截屏")

SUPPORTED_ACTIONS = {
    "goto", "click", "fill", "assert_text", "wait", "press", "hover", "select",
    "check", "uncheck", "scroll", "screenshot", "keyboard", "upload", "assert_visible",
}


# ---------------------------------------------------------------------------
# rule based parsing
# ---------------------------------------------------------------------------
def _segments(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [segment.strip(" \t-*•").strip() for segment in SPLIT_RE.split(raw)]
    return [part for part in parts if part]


def _first_quoted(text: str) -> str:
    match = QUOTED_RE.search(text or "")
    return match.group(1).strip() if match else ""


def _contains_any(text: str, keywords) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _strip_keywords(text: str, keywords) -> str:
    result = text
    for keyword in sorted(keywords, key=len, reverse=True):
        result = re.sub(re.escape(keyword), " ", result, flags=re.I)
    return re.sub(r"\s+", " ", result).strip(" ，,：:、的")


def _rule_steps(natural_language: str) -> list[dict]:
    steps: list[dict] = []
    for segment in _segments(natural_language):
        quoted = _first_quoted(segment)
        url_match = URL_RE.search(segment)
        if _contains_any(segment, KW_GOTO) or url_match:
            target = url_match.group(0) if url_match else _strip_keywords(segment, KW_GOTO)
            steps.append({"action": "goto", "target": target or "/",
                          "description": segment})
            continue
        if _contains_any(segment, KW_FILL):
            remainder = _strip_keywords(segment, KW_FILL)
            value = quoted or remainder
            target = remainder.replace(quoted, "").strip(" ，,：:") if quoted else remainder
            if not target:
                target = "input"
            steps.append({
                "action": "fill",
                "target": target,
                "value": value,
                "description": segment,
            })
            continue
        if _contains_any(segment, KW_ASSERT):
            value = quoted or _strip_keywords(segment, KW_ASSERT)
            steps.append({"action": "assert_text", "target": "body", "value": value,
                          "expect": value, "description": segment})
            continue
        if _contains_any(segment, KW_WAIT):
            duration = DURATION_RE.search(segment)
            millis = 1000
            if duration:
                millis = int(duration.group(1)) * (1000 if duration.group(2) in ("秒", "s") else 1)
            steps.append({"action": "wait", "value": millis, "description": segment})
            continue
        if _contains_any(segment, KW_SELECT):
            steps.append({"action": "select", "target": _strip_keywords(segment, KW_SELECT),
                          "value": quoted, "description": segment})
            continue
        if _contains_any(segment, KW_HOVER):
            steps.append({"action": "hover", "target": _strip_keywords(segment, KW_HOVER),
                          "description": segment})
            continue
        if _contains_any(segment, KW_PRESS):
            steps.append({"action": "press", "target": _strip_keywords(segment, KW_PRESS),
                          "value": quoted or "Enter", "description": segment})
            continue
        if _contains_any(segment, KW_SCREENSHOT):
            steps.append({"action": "screenshot", "description": segment})
            continue
        if _contains_any(segment, KW_CLICK):
            target = quoted or _strip_keywords(segment, KW_CLICK)
            steps.append({"action": "click", "target": target or segment,
                          "description": segment})
            continue
        # unknown short segment -> click, longer sentence -> assertion
        if len(segment) <= 12:
            steps.append({"action": "click", "target": quoted or segment,
                          "description": segment})
        else:
            steps.append({"action": "assert_text", "target": "body",
                          "value": quoted or segment, "description": segment})
    return steps


def _suggest_name(natural_language: str) -> str:
    for segment in _segments(natural_language):
        cleaned = segment.strip(" -_*•")
        if cleaned:
            return cleaned[:60]
    return "AI 生成用例"


# ---------------------------------------------------------------------------
# AI bridge (lazy)
# ---------------------------------------------------------------------------
def _try_ai_steps(natural_language: str, project=None, llm_service=None) -> dict | None:
    payload = {
        "natural_language": natural_language,
        "project_id": getattr(project, "id", None),
        "task": "webui_testcase",
    }
    from apps.web_testing.services.script_builder import ai_enabled

    if llm_service is None and not ai_enabled():
        return None
    try:
        if llm_service is not None and hasattr(llm_service, "chat"):
            reply = llm_service.chat(
                [{"role": "user", "content": f"把下面的操作描述转成 JSON 测试步骤: {natural_language}"}]
            )
            text = getattr(reply, "text", "") or (reply if isinstance(reply, str) else "")
            return _parse_ai_payload(text)
        from apps.ai_core.services.agents.registry import run_agent
    except ImportError:
        return None
    except Exception:  # pragma: no cover - defensive
        logger.info("ai_core unavailable for case generation", exc_info=True)
        return None
    try:
        result = run_agent("webui_testcase", payload)
    except Exception:
        logger.info("webui_testcase agent failed, falling back to rules")
        return None
    return _parse_ai_payload(result)


def _parse_ai_payload(result) -> dict | None:
    data = result
    if isinstance(result, str):
        text = result.strip()
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        text = match.group(1) if match else text
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    steps = data.get("steps")
    if steps is None and isinstance(data.get("cases"), list) and data["cases"]:
        first = data["cases"][0]
        steps = first.get("steps") if isinstance(first, dict) else None
    if not isinstance(steps, list) or not steps:
        return None
    cleaned = []
    for step in steps:
        if not isinstance(step, dict):
            return None
        action = str(step.get("action") or "").lower()
        if action not in SUPPORTED_ACTIONS:
            return None
        item = {"action": action}
        if step.get("target") is not None:
            item["target"] = step["target"]
        if step.get("value") is not None:
            item["value"] = step["value"]
        if step.get("expect") is not None:
            item["expect"] = step["expect"]
        cleaned.append(item)
    name = data.get("name") or data.get("case_name") or ""
    return {"name": str(name), "steps": cleaned, "generated_by": "ai"}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def generate_steps_from_nl(natural_language: str, project=None,
                           llm_service=None) -> dict:
    """Convert natural language to ``{"name", "steps", "generated_by"}``."""
    text = (natural_language or "").strip()
    if not text:
        from apps.common.api.api_exception_handler import BusinessError

        raise BusinessError(message="natural_language 不能为空",
                           code="missing_natural_language")
    ai_result = _try_ai_steps(text, project=project, llm_service=llm_service)
    if ai_result:
        if not ai_result.get("name"):
            ai_result["name"] = _suggest_name(text)
        return ai_result
    return {
        "name": _suggest_name(text),
        "steps": _rule_steps(text),
        "generated_by": "rule",
    }


def generate_case_from_nl(natural_language: str, project, name: str = "",
                          module=None, script_type: str = "playwright",
                          llm_service=None, save: bool = False) -> dict:
    """Generate (optionally persist) a :class:`WebUITestCase` from natural language."""
    generated = generate_steps_from_nl(natural_language, project=project,
                                       llm_service=llm_service)
    if not generated["steps"]:
        from apps.common.api.api_exception_handler import BusinessError

        raise BusinessError(message="无法从描述中解析出测试步骤",
                           code="generation_failed")
    payload = {
        "name": name or generated["name"],
        "steps": generated["steps"],
        "generated_by": generated.get("generated_by", "rule"),
        "description": natural_language,
    }
    if save:
        case = WebUITestCase.objects.create(
            project=project,
            module=module,
            name=payload["name"],
            description=natural_language,
            steps=payload["steps"],
            script_type=script_type or "playwright",
            source="ai",
        )
        payload["case_id"] = case.id
        payload["case"] = case
    return payload
