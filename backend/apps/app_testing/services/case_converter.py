"""AITS 内部步骤 <-> Sonic 步骤格式互转（ARCHITECTURE §2.5）.

AITS 步骤::

    {"action": "tap", "target": "登录按钮", "value": "", "expect": "",
     "description": "点击登录"}

Sonic 步骤（本项目统一采用 ``type/content`` 形态，贯穿全模块）::

    {"type": 0, "content": {"action": "点击", "target": "登录按钮", "value": "",
                            "expect": "", "description": "点击登录"}}

``type`` 取值：

====  ================  =========================================
type  含义              对应的 AITS action
====  ================  =========================================
0     操作步骤          tap/click/input/fill/swipe/back/start_app/stop_app
1     断言步骤          assert/assert_text
2     其他步骤          wait
====  ================  =========================================

双向可逆性：``sonic_steps_to_aits(aits_steps_to_sonic(steps)) == steps``，
前提是 steps 使用**可逆映射范围内的 action**（``tap/input/swipe/assert/wait/
back/start_app/stop_app``）且字段为五个标准字段；``click``/``fill``/
``assert_text`` 是别名，反解时归一到 ``tap``/``input``/``assert``。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: AITS action -> 中文动作名（Sonic 侧展示/存储的名字）
ACTION_TO_LABEL = {
    "tap": "点击",
    "click": "点击",
    "input": "输入",
    "fill": "输入",
    "swipe": "滑动",
    "assert": "断言",
    "assert_text": "断言",
    "wait": "等待",
    "back": "返回",
    "start_app": "启动应用",
    "stop_app": "关闭应用",
}

#: 中文动作名 -> 规范 AITS action（单向归一，保证反解稳定）
LABEL_TO_ACTION = {
    "点击": "tap",
    "单击": "tap",
    "输入": "input",
    "填入": "input",
    "滑动": "swipe",
    "滑动屏幕": "swipe",
    "断言": "assert",
    "断言文本": "assert",
    "等待": "wait",
    "暂停": "wait",
    "返回": "back",
    "后退": "back",
    "启动应用": "start_app",
    "打开应用": "start_app",
    "关闭应用": "stop_app",
    "退出应用": "stop_app",
}

#: Sonic step type
STEP_TYPE_ACTION = 0
STEP_TYPE_ASSERT = 1
STEP_TYPE_OTHER = 2

ACTION_STEP_TYPES = {
    "tap": STEP_TYPE_ACTION,
    "click": STEP_TYPE_ACTION,
    "input": STEP_TYPE_ACTION,
    "fill": STEP_TYPE_ACTION,
    "swipe": STEP_TYPE_ACTION,
    "back": STEP_TYPE_ACTION,
    "start_app": STEP_TYPE_ACTION,
    "stop_app": STEP_TYPE_ACTION,
    "assert": STEP_TYPE_ASSERT,
    "assert_text": STEP_TYPE_ASSERT,
    "wait": STEP_TYPE_OTHER,
}

#: 反解时可接受的 type -> action 兜底（type 缺失时使用）
STEP_TYPE_FALLBACK_ACTION = {
    STEP_TYPE_ACTION: "tap",
    STEP_TYPE_ASSERT: "assert",
    STEP_TYPE_OTHER: "wait",
}

#: AITS 步骤的标准字段（顺序固定，保证 JSON 幂等）
STEP_FIELDS = ("action", "target", "value", "expect", "description")


def normalize_step(step) -> dict:
    """Return a canonical AITS step (all five fields present)."""
    step = step if isinstance(step, dict) else {}
    normalized = {field: _text(step.get(field)) for field in STEP_FIELDS}
    action = normalized["action"].lower()
    if action in LABEL_TO_ACTION:  # tolerate Chinese actions on input
        action = LABEL_TO_ACTION[action]
    normalized["action"] = action or "tap"
    return normalized


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _step_type(action: str) -> int:
    return ACTION_STEP_TYPES.get(action, STEP_TYPE_ACTION)


# ---------------------------------------------------------------------------
# AITS -> Sonic
# ---------------------------------------------------------------------------
def aits_steps_to_sonic(steps) -> list:
    """Convert AITS internal steps to the Sonic compatible step format."""
    if not steps:
        return []
    if not isinstance(steps, (list, tuple)):
        raise ValueError("steps 必须是数组")
    converted = []
    for raw in steps:
        step = normalize_step(raw)
        converted.append(
            {
                "type": _step_type(step["action"]),
                "content": {
                    "action": ACTION_TO_LABEL.get(step["action"], step["action"]),
                    "target": step["target"],
                    "value": step["value"],
                    "expect": step["expect"],
                    "description": step["description"],
                },
            }
        )
    return converted


# ---------------------------------------------------------------------------
# Sonic -> AITS
# ---------------------------------------------------------------------------
def sonic_steps_to_aits(steps) -> list:
    """Convert Sonic steps back to AITS internal steps."""
    if not steps:
        return []
    if not isinstance(steps, (list, tuple)):
        raise ValueError("steps 必须是数组")
    converted = []
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        # Sonic may wrap the payload as {"step": {...}} / {"step": {"type", "content"}}
        node = raw
        for wrapper in ("step", "data"):
            inner = node.get(wrapper)
            if isinstance(inner, dict) and ("content" in inner or "action" in inner):
                node = inner
                break
        content = node.get("content")
        if isinstance(content, str):  # 极少见：content 直接是动作名
            content = {"action": content}
        if not isinstance(content, dict):
            content = {}
        # content 也允许扁平写法（action/target 直接挂在节点上）
        merged = {**node, **content}
        label = _text(merged.get("action") or merged.get("type"))
        action = LABEL_TO_ACTION.get(label) or LABEL_TO_ACTION.get(label.lower())
        if not action:
            raw_action = _text(merged.get("action")).lower()
            action = raw_action if raw_action in ACTION_TO_LABEL else ""
        if not action:
            action = STEP_TYPE_FALLBACK_ACTION.get(node.get("type"), "tap")
        converted.append(
            {
                "action": action,
                "target": _text(merged.get("target")),
                "value": _text(merged.get("value")),
                "expect": _text(merged.get("expect")),
                "description": _text(merged.get("description")),
            }
        )
    return converted


def sync_case_steps(case, save=True) -> list:
    """Refresh ``case.sonic_steps`` from ``case.steps`` (used on save/generate)."""
    sonic_steps = aits_steps_to_sonic(case.steps or [])
    if save and case.sonic_steps != sonic_steps:
        case.sonic_steps = sonic_steps
        case.save(update_fields=["sonic_steps", "updated_at"])
    return sonic_steps


# ---------------------------------------------------------------------------
# suite payload
# ---------------------------------------------------------------------------
def build_suite_payload(suite, cases, project) -> dict:
    """Assemble the payload required by Sonic ``runSuite``.

    ``suite`` may be an :class:`~apps.app_testing.models.AppTestSuite` (preferred)
    or ``None`` for an ad-hoc case list; ``cases`` is an iterable of
    :class:`~apps.app_testing.models.AppTestCase`.
    """
    cases = list(cases or [])
    device_config = dict(getattr(suite, "device_config", None) or {}) if suite else {}
    application = getattr(suite, "application", None) if suite else None
    if application is None:
        application = next((case.application for case in cases if case.application_id), None)

    sonic_project_id = ""
    if project is not None:
        sonic_project_id = getattr(project, "sonic_project_id", "") or ""
    if not sonic_project_id:
        from django.conf import settings

        sonic_project_id = getattr(settings, "SONIC_PROJECT_ID", "") or ""

    platform = (
        device_config.get("platform")
        or getattr(application, "platform", "")
        or ""
    )
    payload = {
        "sonicProjectId": str(sonic_project_id or ""),
        "projectId": str(sonic_project_id or ""),
        "suiteName": getattr(suite, "name", "") or "AITS App 测试",
        "suiteDescription": getattr(suite, "description", "") or "",
        "deviceId": str(device_config.get("device_id") or device_config.get("deviceId") or ""),
        "udid": str(
            device_config.get("udid")
            or device_config.get("device_udid")
            or device_config.get("deviceUdid")
            or ""
        ),
        "platform": platform or "",
        "appPackage": getattr(application, "app_identifier", "") or "",
        "appVersion": getattr(application, "app_version", "") or "",
        "cases": [
            {
                "caseId": case.id,
                "name": case.name,
                "steps": case.sonic_steps or aits_steps_to_sonic(case.steps or []),
                "aitsSteps": case.steps or [],
            }
            for case in cases
        ],
    }
    payload["deviceConfig"] = device_config
    payload["caseIds"] = [case.id for case in cases]
    return payload
