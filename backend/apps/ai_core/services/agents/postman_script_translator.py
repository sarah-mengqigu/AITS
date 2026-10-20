"""postman_translator Agent：把 Postman ``pm.*`` 脚本规则化转换为 AITS 断言。

优先使用确定性规则解析（``pm.response.to.have.status`` /
``pm.expect(...).to.eql`` / ``pm.environment.set`` 等），
规则未覆盖的写法回退到 LLM 兜底解析。
"""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from apps.ai_core.services.agents.base import BaseAgent

_TEST_RE = re.compile(r"pm\.test\s*\(\s*(['\"])(.+?)\1")
_STATUS_RE = re.compile(r"pm\.response\.to\.have\.status\s*\(\s*(\d{3})\s*\)")
_HEADER_RE = re.compile(
    r"pm\.response\.to\.have\.header\s*\(\s*(['\"])(.+?)\1\s*(?:,\s*(['\"])(.*?)\3\s*)?\)"
)
_EXPECT_RE = re.compile(
    r"pm\.expect\s*\((.+?)\)\s*\.to\.([A-Za-z_][A-Za-z0-9_.]*)\s*(?:\(([^)]*)\))?", re.S
)
_ENV_SET_RE = re.compile(
    r"pm\.(?:environment|collectionVariables|globals|variables)\.set\s*\(\s*(['\"])(.+?)\1\s*,\s*(.+?)\s*\)\s*;"
)
_JSON_PATH_RE = re.compile(
    r"pm\.response\.json\(\)((?:\.[A-Za-z_$][\w$]*|\[\s*['\"][^'\"]+['\"]\s*\]|\[\d+\])+)"
)
_HEADER_GET_RE = re.compile(
    r"pm\.response\.headers\.get\(\s*(['\"])(.+?)\1\s*\)"
)

_EQ_MATCHERS = {"eql", "equal", "be.eql", "be.equal", "deep.equal", "deep.eql"}
_ABOVE_MATCHERS = {"be.above", "be.greaterthan", "be.gt"}
_BELOW_MATCHERS = {"be.below", "be.lessthan", "be.lt"}
_INCLUDE_MATCHERS = {"include", "contain", "contains", "string"}
_LENGTH_MATCHERS = {"have.lengthof", "have.length", "lengthof"}


class PostmanTranslatorState(TypedDict, total=False):
    payload: dict
    project: Any
    prompt: str
    retrieved: list
    llm_text: str
    llm_data: Any
    usage: list
    result: Any


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------
def parse_literal(raw: str) -> Any:
    """Turn a JS literal inside ``pm.*`` calls into a Python value."""
    if raw is None:
        return None
    text = str(raw).strip().rstrip(";").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text in {"true", "false"}:
        return text == "true"
    if text in {"null", "undefined"}:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _render(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)


def normalize_expression(expression: str) -> str:
    text = str(expression or "").strip()
    replacements = (
        ("pm.response.json()", "response.json"),
        ("pm.response.text()", "response.text"),
        ("pm.response.code", "response.status_code"),
        ("pm.response.headers.get(", "response.headers.get("),
        ("pm.response", "response"),
        ("pm.environment.get", "env.get"),
        ("pm.collectionVariables.get", "collection.get"),
        ("pm.globals.get", "globals.get"),
        ("pm.variables.get", "vars.get"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _json_path(value_expression: str) -> str | None:
    match = _JSON_PATH_RE.search(str(value_expression or ""))
    if not match:
        return None
    path = match.group(1)
    path = re.sub(r"\[\s*['\"]([^'\"]+)['\"]\s*\]", r".\1", path)
    path = re.sub(r"\[(\d+)\]", r".\1", path)
    return path.strip(".")


def _message_at(script: str, position: int) -> str:
    message = ""
    for match in _TEST_RE.finditer(script):
        if match.start() <= position:
            message = match.group(2)
        else:
            break
    return message


def _expected_for(matcher: str, args: str | None):
    lowered = matcher.lower()
    if lowered in _EQ_MATCHERS:
        return "==", parse_literal(args)
    if lowered in _INCLUDE_MATCHERS:
        return "contains", parse_literal(args)
    if lowered in _ABOVE_MATCHERS:
        return ">", parse_literal(args)
    if lowered in _BELOW_MATCHERS:
        return "<", parse_literal(args)
    if lowered in _LENGTH_MATCHERS:
        return "length ==", parse_literal(args)
    if lowered in {"have.property", "have.ownproperty"}:
        return "has property", parse_literal(args)
    if lowered in {"be.a", "be.an"}:
        return "is a", parse_literal(args)
    if lowered == "match":
        return "matches", parse_literal(args)
    if lowered in {"be.true", "true"}:
        return "==", True
    if lowered in {"be.false", "false"}:
        return "==", False
    if lowered in {"be.ok", "ok"}:
        return "is truthy", True
    if lowered in {"exist", "not.exist"}:
        return "exist", True
    if lowered in {"be.empty"}:
        return "length ==", 0
    return ".", parse_literal(args)


def parse_postman_script(script: str) -> dict:
    """Rule based translation; always returns the three contract keys."""
    script = script or ""
    validations: list[dict] = []
    extracts: list[dict] = []
    variables: dict = {}

    def add_validation(expression: str, expected, message: str, operator: str = "=="):
        entry = {
            "expression": expression,
            "expected": expected,
            "message": message or f"{expression} 校验",
            "operator": operator,
            "source": "rule",
        }
        if entry not in validations:
            validations.append(entry)

    for match in _STATUS_RE.finditer(script):
        status = int(match.group(1))
        add_validation(
            f"response.status_code == {status}",
            status,
            _message_at(script, match.start()) or f"状态码为 {status}",
        )

    for match in _HEADER_RE.finditer(script):
        header = match.group(2)
        expected = match.group(4)
        add_validation(
            f"response.headers[{json.dumps(header)}]",
            expected,
            _message_at(script, match.start()) or f"响应头包含 {header}",
            "header exists",
        )

    for match in _EXPECT_RE.finditer(script):
        raw_expression = match.group(1)
        matcher = match.group(2)
        args = match.group(3)
        expression = normalize_expression(raw_expression)
        operator, expected = _expected_for(matcher, args)
        rendered = f"{expression} {operator}"
        if expected is not None or operator in {"==", "contain", "contains"}:
            rendered = f"{rendered} {_render(expected)}"
        add_validation(
            rendered,
            expected,
            _message_at(script, match.start()) or f"{expression} 断言",
            operator,
        )

    for match in _ENV_SET_RE.finditer(script):
        name = match.group(2)
        value_expression = match.group(3)
        path = _json_path(value_expression)
        if path:
            extract = {"name": name, "path": path, "source": "body"}
        else:
            header_match = _HEADER_GET_RE.search(value_expression)
            if header_match:
                extract = {"name": name, "path": header_match.group(2), "source": "header"}
            elif "pm.response.text()" in value_expression:
                extract = {"name": name, "path": "", "source": "text"}
            elif "pm.response.code" in value_expression:
                extract = {"name": name, "path": "status_code", "source": "response"}
            else:
                extract = None
                variables[name] = parse_literal(value_expression)
        if extract and extract not in extracts:
            extracts.append(extract)

    return {
        "validations": validations,
        "extracts": extracts,
        "variables": variables,
        "source": "rule",
    }


class PostmanScriptTranslator(BaseAgent):
    name = "postman_translator"
    description = "把 Postman 的 pm.test/pm.expect/pm.environment.set 脚本转换为 AITS 断言、提取与变量"
    stream_channel = "postman_translation"
    task_type = "postman_translate"
    state_schema = PostmanTranslatorState

    def retrieval_query(self, state) -> str:
        return ""

    def build_prompt(self, payload: dict) -> str:
        script = payload.get("script") or ""
        return (
            f"[agent:{self.name}]\n"
            "请解析下面的 Postman 测试脚本，输出 JSON：\n"
            '{"validations": [{"expression": "...", "expected": "...", "message": "..."}],'
            ' "extracts": [{"name": "...", "path": "...", "source": "body"}], "variables": {}}\n'
            f"脚本：\n{script}\n"
            "请仅输出 JSON。"
        )

    # ------------------------------------------------------------------
    def compose_result(self, payload: dict, llm_data, state) -> dict:
        parsed = parse_postman_script(payload.get("script") or "")
        validations = list(parsed["validations"])
        extracts = list(parsed["extracts"])
        variables = dict(parsed["variables"])

        if isinstance(llm_data, dict):
            llm_validations = llm_data.get("validations")
            if isinstance(llm_validations, list):
                for item in llm_validations:
                    if not isinstance(item, dict):
                        continue
                    expression = item.get("expression")
                    if not expression:
                        continue
                    entry = {
                        "expression": str(expression),
                        "expected": item.get("expected"),
                        "message": str(item.get("message") or expression),
                        "operator": str(item.get("operator") or "=="),
                        "source": "llm",
                    }
                    if not any(
                        existing["expression"] == entry["expression"]
                        for existing in validations
                    ):
                        validations.append(entry)
            llm_extracts = llm_data.get("extracts")
            if isinstance(llm_extracts, list):
                for item in llm_extracts:
                    if isinstance(item, dict) and item.get("name"):
                        candidate = {
                            "name": str(item["name"]),
                            "path": str(item.get("path") or ""),
                            "source": str(item.get("source") or "body"),
                        }
                        if candidate not in extracts:
                            extracts.append(candidate)
            llm_variables = llm_data.get("variables")
            if isinstance(llm_variables, dict):
                for key, value in llm_variables.items():
                    variables.setdefault(str(key), value)

        return {
            "validations": validations,
            "extracts": extracts,
            "variables": variables,
            "source": "rule+llm" if any(v["source"] == "llm" for v in validations) else "rule",
        }
