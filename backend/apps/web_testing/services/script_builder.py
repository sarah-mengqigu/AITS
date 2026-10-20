"""Playwright / MidScene script generation for Web UI test cases.

Public API (stable contract used by views, tasks and other modules)::

    generate_playwright_script(case, pom_pages=None) -> str
    generate_midscene_script(case) -> str
    build_script(case, script_type=None, pom_pages=None) -> (text, source)

Design notes
------------
* AI generation is attempted first through ``apps.ai_core`` but the import is
  strictly lazy: when ai_core is missing, disabled or raises, we fall back to a
  deterministic template. Tests never depend on a working LLM.
* Locators prefer the Page Object Model (``WebPage`` / ``WebElement``) and use
  ``alternatives`` as fall-backs inside the generated helper ``locate()``.
* Generated Python is *valid* Python: every playwright script is compile checked
  before being returned (a failing AI script is replaced by the template).
"""

from __future__ import annotations

import json
import logging
import re

import yaml
from django.conf import settings

from apps.common.api.api_exception_handler import BusinessError

logger = logging.getLogger(__name__)

SUPPORTED_SCRIPT_TYPES = ("playwright", "midscene")
SUPPORTED_STYLES = ("sync", "async")

#: Playwright code path per locator type (``{v}`` is replaced by the value).
LOCATOR_BUILDERS = {
    "css": 'page.locator({v})',
    "xpath": 'page.locator("xpath=" + {v})',
    "text": "page.get_by_text({v})",
    "role": "page.get_by_role({v})",
    "id": 'page.locator("#" + {v})',
    "testid": "page.get_by_test_id({v})",
}

DEFAULT_WAIT_MS = 1000


# ---------------------------------------------------------------------------
# AI availability (lazy, never raises)
# ---------------------------------------------------------------------------
def ai_enabled() -> bool:
    """Return True only when a real (non-mock) LLM is configured.

    * ``AI_MOCK_MODE`` (test/offline) -> template generation, so tests never
      depend on ``ai_core`` nor on an external LLM.
    * ``ai_core`` missing / not configured (only mock providers) -> template.
    """
    if bool(getattr(settings, "AI_MOCK_MODE", False)):
        return False
    try:
        from apps.ai_core.models import LLMConfiguration
    except Exception:
        return False
    try:
        return (
            LLMConfiguration.objects.filter(is_active=True)
            .exclude(provider="mock")
            .exists()
        )
    except Exception:  # pragma: no cover - schema not migrated yet
        return False


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _slug(text, fallback="item") -> str:
    """Make a python/identifier friendly slug (keeps CJK characters)."""
    raw = str(text or "").strip()
    cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", raw).strip("_")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"{fallback}_{cleaned}"
    return cleaned[:60]


def _py(value) -> str:
    """Render a python literal (JSON is a valid subset for our value set)."""
    return json.dumps(value, ensure_ascii=False)


def _step_list(case) -> list:
    steps = getattr(case, "steps", None) or []
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _case_browser(case) -> str:
    browser = getattr(case, "browser", None) or "chromium"
    return browser if browser in ("chromium", "firefox", "webkit") else "chromium"


def _step_label(index: int, step: dict) -> str:
    action = step.get("action") or "step"
    target = step.get("target") or step.get("value") or ""
    if isinstance(target, dict):
        target = target.get("name") or target.get("selector") or ""
    label = f"步骤 {index}: {action}"
    if target:
        label += f" {target}"
    return label.replace("\n", " ")[:120]


def _target_key(step: dict) -> str:
    target = step.get("target")
    if isinstance(target, dict):
        page = target.get("page") or ""
        name = target.get("name") or target.get("element") or ""
        if page and name:
            return f"{page}.{name}"
        if name:
            return str(name)
        return str(target.get("selector") or target.get("locator") or "")
    if target is None:
        return str(step.get("selector") or step.get("locator") or "")
    return str(target)


def _step_value(step: dict):
    value = step.get("value")
    if value is None:
        value = step.get("text")
    if value is None:
        value = step.get("expect")
    return value


# ---------------------------------------------------------------------------
# POM resolution
# ---------------------------------------------------------------------------
def collect_pom(case, pom_pages=None) -> dict:
    """Build the POM payload embedded in generated scripts.

    Returns ``{"pages": [...], "elements": {key: [[locator_type, value], ...]}}``.
    """
    pages = pom_pages
    if pages is None:
        from apps.web_testing.models import WebPage

        queryset = WebPage.objects.all()
        project_id = getattr(case, "project_id", None)
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        wanted = getattr(case, "pom_page_ids", None) or []
        if wanted:
            selected = list(queryset.filter(id__in=wanted).prefetch_related("elements"))
            if selected:
                queryset = queryset.filter(id__in=[page.id for page in selected])
        pages = list(queryset.prefetch_related("elements").order_by("id"))

    payload_pages = []
    elements: dict[str, list] = {}
    for page in pages or []:
        page_slug = _slug(page.name, fallback=f"page_{page.id}")
        payload_elements = []
        for element in page.elements.all():
            locators = [[kind, value] for kind, value in element.locators()]
            element_slug = _slug(element.name, fallback=f"element_{element.id}")
            payload_elements.append(
                {
                    "name": element.name,
                    "slug": element_slug,
                    "locators": locators,
                }
            )
            # page-scoped key is always unique; bare name only when unambiguous
            elements.setdefault(f"{page.name}.{element.name}", locators)
            elements.setdefault(f"{page_slug}.{element_slug}", locators)
            elements.setdefault(f"{page_slug}.{element.name}", locators)
            elements.setdefault(element.name, locators)
            elements.setdefault(element_slug, locators)
        payload_pages.append(
            {
                "id": page.id,
                "name": page.name,
                "slug": page_slug,
                "url": page.url,
                "elements": payload_elements,
            }
        )
    return {"pages": payload_pages, "elements": elements}


def _is_pom_key(pom: dict, key: str) -> bool:
    return bool(key) and key in pom.get("elements", {})


# ---------------------------------------------------------------------------
# Playwright generation
# ---------------------------------------------------------------------------
def _locate_expr(pom: dict, target: str, style: str) -> str:
    """Return the python expression resolving ``target`` to a Locator."""
    if _is_pom_key(pom, target):
        return f"locate(page, {_py(target)})"
    if not target:
        return 'page.locator("body")'
    if target.startswith(("/", "//", "(", "./")):
        return f'page.locator({_py("xpath=" + target)})'
    if target.startswith("#") or target.startswith(".") or "[" in target:
        return f"page.locator({_py(target)})"
    return f'locate(page, {_py(target)})'


def _playwright_statements(case, pom: dict, style: str) -> list[str]:
    """Render the case steps (plus assertions) as indented python statements."""
    await_ = "await " if style == "async" else ""
    lines: list[str] = []
    for index, step in enumerate(_step_list(case), start=1):
        action = str(step.get("action") or "").lower()
        target = _target_key(step)
        value = _step_value(step)
        lines.append(f"            # {_step_label(index, step)}")
        if action == "goto":
            url = str(value or target or "")
            lines.append(f"            {await_}page.goto({_py(url)})")
        elif action == "click":
            lines.append(f"            {await_}{_locate_expr(pom, target, style)}.click()")
        elif action == "fill":
            locator = _locate_expr(pom, target, style)
            lines.append(f"            {await_}{locator}.fill({_py('' if value is None else value)})")
        elif action == "assert_text":
            locator = _locate_expr(pom, target, style)
            expected = "" if value is None else str(value)
            lines.append(
                f"            {await_}expect({locator}).to_contain_text({_py(expected)})"
            )
        elif action == "assert_visible":
            locator = _locate_expr(pom, target, style)
            lines.append(f"            {await_}expect({locator}).to_be_visible()")
        elif action == "wait":
            millis = _to_int(value, DEFAULT_WAIT_MS)
            lines.append(f"            {await_}page.wait_for_timeout({millis})")
        elif action == "press":
            locator = _locate_expr(pom, target, style)
            lines.append(f"            {await_}{locator}.press({_py(str(value or 'Enter'))})")
        elif action == "select":
            locator = _locate_expr(pom, target, style)
            lines.append(f"            {await_}{locator}.select_option({_py(str(value or ''))})")
        elif action == "hover":
            lines.append(f"            {await_}{_locate_expr(pom, target, style)}.hover()")
        elif action == "check":
            lines.append(f"            {await_}{_locate_expr(pom, target, style)}.check()")
        elif action == "uncheck":
            lines.append(f"            {await_}{_locate_expr(pom, target, style)}.uncheck()")
        elif action == "scroll":
            locator = _locate_expr(pom, target, style)
            lines.append(f"            {await_}{locator}.scroll_into_view_if_needed()")
        elif action == "keyboard":
            lines.append(
                f"            {await_}page.keyboard.press({_py(str(value or 'Enter'))})"
            )
        elif action == "upload":
            locator = _locate_expr(pom, target, style)
            lines.append(f"            {await_}{locator}.set_input_files({_py(str(value or ''))})")
        elif action == "screenshot":
            name = str(value or f"screenshots/step_{index}.png")
            lines.append(f"            {await_}page.screenshot(path={_py(name)})")
        else:
            lines.append(f"            {await_}page.wait_for_timeout({DEFAULT_WAIT_MS})")
        # optional assertion attached to a step
        expect = step.get("expect")
        if expect is not None and action not in ("assert_text", "assert_visible"):
            lines.append(
                f"            {await_}expect(page.locator(\"body\")).to_contain_text("
                f"{_py(str(expect))})"
            )
        lines.append("")

    for assertion in getattr(case, "assertions", None) or []:
        if isinstance(assertion, dict):
            kind = str(assertion.get("type") or assertion.get("action") or "text").lower()
            value = assertion.get("value") or assertion.get("expect") or ""
            target = _target_key(assertion)
        else:
            kind, value, target = "text", str(assertion), ""
        lines.append(f"            # 断言: {kind}")
        if kind in ("url", "page_url"):
            lines.append(f"            {await_}expect(page).to_have_url({_py(str(value))})")
        elif kind in ("title", "page_title"):
            lines.append(f"            {await_}expect(page).to_have_title({_py(str(value))})")
        elif kind in ("visible", "assert_visible") and target:
            lines.append(
                f"            {await_}expect({_locate_expr(pom, target, style)}).to_be_visible()"
            )
        else:
            locator = _locate_expr(pom, target, style) if target else 'page.locator("body")'
            lines.append(
                f"            {await_}expect({locator}).to_contain_text({_py(str(value))})"
            )
        lines.append("")

    if not lines:
        lines.append("            # 用例没有可执行步骤，仅打开页面")
        lines.append(f'            {await_}page.wait_for_timeout({DEFAULT_WAIT_MS})')
        lines.append("")
    return lines


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


PLAYWRIGHT_HEADER_SYNC = '''"""AITS 自动生成的 Playwright 脚本（sync_api）。"""

from playwright.sync_api import expect, sync_playwright
'''

PLAYWRIGHT_HEADER_ASYNC = '''"""AITS 自动生成的 Playwright 脚本（async_api）。"""

import asyncio

from playwright.async_api import async_playwright, expect
'''

PLAYWRIGHT_HELPERS = '''

def _build_locator(page, locator_type, value):
    """按定位类型构建 Locator（css/xpath/text/role/id/testid）。"""
    if locator_type == "css":
        return page.locator(value)
    if locator_type == "xpath":
        return page.locator("xpath=" + value)
    if locator_type == "text":
        return page.get_by_text(value)
    if locator_type == "role":
        return page.get_by_role(value)
    if locator_type == "id":
        return page.locator("#" + value)
    if locator_type == "testid":
        return page.get_by_test_id(value)
    return page.locator(value)


def locate(page, key):
    """解析 POM 元素：主定位器优先，失败时依次回退到备选定位器。"""
    candidates = POM_ELEMENTS.get(str(key))
    if not candidates:
        if str(key).startswith(("/", "//", "(")):
            return _build_locator(page, "xpath", str(key))
        return _build_locator(page, "css", str(key))
    for locator_type, value in candidates:
        locator = _build_locator(page, locator_type, value)
        try:
            if locator.count() > 0:
                return locator
        except Exception:
            continue
    locator_type, value = candidates[0]
    return _build_locator(page, locator_type, value)
'''


def _render_playwright(case, pom: dict, style: str) -> str:
    browser = _case_browser(case)
    headless = bool(getattr(case, "headless", True))
    pom_json = json.dumps(pom.get("elements", {}), ensure_ascii=False, indent=4)
    body = _playwright_statements(case, pom, style)
    header = PLAYWRIGHT_HEADER_ASYNC if style == "async" else PLAYWRIGHT_HEADER_SYNC
    meta = [
        "",
        f"# 用例: {getattr(case, 'name', '')}",
        f"# 脚本类型: playwright ({style})",
        f"# 浏览器: {browser}  headless: {headless}",
        "",
        f"POM_ELEMENTS = {pom_json}",
        PLAYWRIGHT_HELPERS,
        "",
    ]
    statements = "\n".join(body)
    if style == "async":
        entry = (
            "\n\nasync def run(headless=True):\n"
            "    async with async_playwright() as playwright:\n"
            f"        browser = await playwright.{browser}.launch(headless=headless)\n"
            "        context = await browser.new_context()\n"
            "        page = await context.new_page()\n"
            "        try:\n"
            f"{statements}"
            "        finally:\n"
            "            await context.close()\n"
            "            await browser.close()\n"
            "\n\nif __name__ == \"__main__\":\n"
            "    asyncio.run(run())\n"
        )
    else:
        entry = (
            "\n\ndef run(headless=True):\n"
            "    with sync_playwright() as playwright:\n"
            f"        browser = playwright.{browser}.launch(headless=headless)\n"
            "        context = browser.new_context()\n"
            "        page = context.new_page()\n"
            "        try:\n"
            f"{statements}"
            "        finally:\n"
            "            context.close()\n"
            "            browser.close()\n"
            "\n\nif __name__ == \"__main__\":\n"
            "    run()\n"
        )
    return header + "\n".join(meta) + entry


def generate_playwright_script(case, pom_pages=None) -> str:
    """Return a runnable Playwright python script for ``case``.

    AI output is used when ai_core is available *and* the returned text is a
    valid playwright script; otherwise the deterministic template is returned.
    """
    ai_script = _try_ai_script(case, "webui_playwright", kind="playwright")
    if ai_script:
        return ai_script
    pom = collect_pom(case, pom_pages)
    return _render_playwright(case, pom, style="sync")


def generate_async_playwright_script(case, pom_pages=None) -> str:
    """Variant of :func:`generate_playwright_script` using ``async_api``."""
    pom = collect_pom(case, pom_pages)
    return _render_playwright(case, pom, style="async")


# ---------------------------------------------------------------------------
# MidScene generation
# ---------------------------------------------------------------------------
def _midscene_flow_item(step: dict) -> dict | None:
    action = str(step.get("action") or "").lower()
    target = _target_key(step)
    value = _step_value(step)
    value_text = "" if value is None else str(value)
    if action == "goto":
        return {"ai": f"打开页面 {value_text or target}"}
    if action == "click":
        return {"ai": f"点击 {target}"}
    if action == "fill":
        return {"ai": f"在 {target} 输入 {value_text}"}
    if action == "assert_text":
        return {"aiAssert": value_text or f"页面显示 {target}"}
    if action == "assert_visible":
        return {"aiAssert": f"元素 {target} 可见"}
    if action == "wait":
        return {"aiWaitFor": f"等待 {target or value_text or '页面加载完成'}",
                "timeout": _to_int(value, DEFAULT_WAIT_MS)}
    if action == "press":
        return {"ai": f"在 {target} 按下 {value_text or 'Enter'}"}
    if action == "select":
        return {"ai": f"在 {target} 选择 {value_text}"}
    if action == "hover":
        return {"ai": f"鼠标悬停在 {target}"}
    if action in ("keyboard",):
        return {"ai": f"按下键盘 {value_text or 'Enter'}"}
    if not action:
        return None
    return {"ai": f"执行操作 {action} {target} {value_text}".strip()}


def build_midscene_document(case) -> dict:
    """Deterministic MidScene YAML document (``target`` + ``tasks[].flow``)."""
    pom = collect_pom(case)
    start_url = ""
    steps = _step_list(case)
    for step in steps:
        if str(step.get("action") or "").lower() == "goto":
            start_url = str(_step_value(step) or _target_key(step) or "")
            break
    if not start_url:
        for page in pom.get("pages", []):
            if page.get("url"):
                start_url = page["url"]
                break

    flow = []
    for step in steps:
        item = _midscene_flow_item(step)
        if item:
            flow.append(item)
    for assertion in getattr(case, "assertions", None) or []:
        if isinstance(assertion, dict):
            text = assertion.get("value") or assertion.get("expect") or ""
        else:
            text = str(assertion)
        if text:
            flow.append({"aiAssert": str(text)})
    if not flow:
        flow = [{"ai": f"打开并检查页面 {getattr(case, 'name', '')}"}]

    document = {
        "target": {"url": start_url, "browser": _case_browser(case)},
        "tasks": [{"name": getattr(case, "name", "") or "MidScene 任务", "flow": flow}],
    }
    return document


def generate_midscene_script(case) -> str:
    """Return a MidScene **YAML** script for ``case`` (deterministic structure)."""
    ai_script = _try_ai_script(case, "midscene_script", kind="midscene")
    if ai_script:
        return ai_script
    document = build_midscene_document(case)
    header = (
        f"# AITS 自动生成的 MidScene 脚本\n"
        f"# 用例: {getattr(case, 'name', '')}\n"
    )
    return header + yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def generate_midscene_python_script(case) -> str:
    """Return the same MidScene plan rendered as a python module."""
    document = build_midscene_document(case)
    payload = json.dumps(document, ensure_ascii=False, indent=4)
    return (
        '"""AITS 自动生成的 MidScene Python 脚本。"""\n'
        "import json\n\n"
        f"MIDSCENE_PLAN = json.loads(r'''{payload}''')\n\n\n"
        "def build_tasks():\n"
        '    """返回 MidScene tasks 列表（供 midscene agent 消费）。"""\n'
        '    return MIDSCENE_PLAN["tasks"]\n\n\n'
        'if __name__ == "__main__":\n'
        "    print(json.dumps(build_tasks(), ensure_ascii=False, indent=2))\n"
    )


# ---------------------------------------------------------------------------
# AI bridge (lazy, never raises)
# ---------------------------------------------------------------------------
def _try_ai_script(case, agent_name: str, kind: str = "playwright") -> str | None:
    """Try to obtain a script from ai_core agents; return ``None`` on any issue.

    The ai_core import happens *before* touching the database so the template
    path stays cheap when the AI module is not installed.
    """
    if not ai_enabled():
        return None
    try:
        from apps.ai_core.services.agents.registry import run_agent
    except ImportError:
        return None
    except Exception:  # pragma: no cover - defensive
        logger.warning("ai_core import failed", exc_info=True)
        return None

    payload = {
        "case_id": getattr(case, "id", None),
        "case_name": getattr(case, "name", ""),
        "description": getattr(case, "description", ""),
        "steps": _step_list(case),
        "assertions": getattr(case, "assertions", None) or [],
        "project_id": getattr(case, "project_id", None),
        "pom": collect_pom(case),
    }
    try:
        result = run_agent(agent_name, payload)
    except Exception:
        logger.info("ai agent %s unavailable, falling back to template", agent_name)
        return None

    text = None
    if isinstance(result, dict):
        for key in ("script", "content", "text", "code", "output"):
            if isinstance(result.get(key), str) and result[key].strip():
                text = result[key]
                break
    elif isinstance(result, str):
        text = result
    if not text:
        return None
    text = _strip_fence(text)
    if kind == "playwright":
        if "playwright" not in text.lower():
            return None
        try:
            compile(text, "<ai-playwright>", "exec")
        except SyntaxError:
            return None
        return text
    try:
        parsed = yaml.safe_load(text)
    except Exception:
        return None
    if not isinstance(parsed, dict) or "tasks" not in parsed:
        return None
    return text


def _strip_fence(text: str) -> str:
    match = re.search(r"```(?:json|yaml|yml|python)?\s*(.*?)```", text or "", re.S)
    return match.group(1).strip() if match else (text or "").strip()


# ---------------------------------------------------------------------------
# unified entrypoint
# ---------------------------------------------------------------------------
def build_script(case, script_type: str | None = None, pom_pages=None) -> tuple[str, str]:
    """Generate a script and report its provenance.

    Returns ``(script_text, source)`` where *source* is ``"ai"`` or ``"template"``.
    """
    script_type = (script_type or getattr(case, "script_type", None) or "playwright").lower()
    if script_type not in SUPPORTED_SCRIPT_TYPES:
        raise BusinessError(
            message=f"script_type 仅支持 {list(SUPPORTED_SCRIPT_TYPES)}",
            code="invalid_script_type",
        )
    if script_type == "playwright":
        ai_script = _try_ai_script(case, "webui_playwright", kind="playwright")
        if ai_script:
            return ai_script, "ai"
        return _render_playwright(case, collect_pom(case, pom_pages), style="sync"), "template"
    ai_script = _try_ai_script(case, "midscene_script", kind="midscene")
    if ai_script:
        return ai_script, "ai"
    return generate_midscene_script(case), "template"
