"""Robust JSON / YAML parsing used by importers, agents and script runners."""

from __future__ import annotations

import json
import re

import yaml

from apps.common.api.api_exception_handler import BusinessError

_FENCE_RE = re.compile(r"```(?:json|yaml|yml|python)?\s*(.*?)```", re.S)


def strip_code_fence(text: str) -> str:
    """Return the content of the first fenced block, else the raw text."""
    if not text:
        return ""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def parse_json(text: str, *, allow_yaml: bool = False):
    """Parse JSON, optionally falling back to YAML (YAML is a JSON superset)."""
    if isinstance(text, (dict, list)):
        return text
    raw = strip_code_fence(text)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        if allow_yaml:
            try:
                return yaml.safe_load(raw)
            except yaml.YAMLError:
                pass
        raise BusinessError(message="JSON 解析失败，请检查格式", code="invalid_json")


def parse_yaml(text: str):
    if isinstance(text, (dict, list)):
        return text
    raw = strip_code_fence(text)
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise BusinessError(message=f"YAML 解析失败: {exc}", code="invalid_yaml") from exc


def parse_any(text: str):
    """Try JSON then YAML."""
    return parse_json(text, allow_yaml=True)


def extract_first_object(text: str):
    """Best-effort extraction of the first JSON object/array in an LLM reply."""
    if not text:
        return None
    raw = strip_code_fence(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for opening, closing in (("{", "}"), ("[", "]")):
        start = raw.find(opening)
        if start == -1:
            continue
        depth = 0
        for idx in range(start, len(raw)):
            char = raw[idx]
            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    candidate = raw[start : idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    return None


def dumps_yaml(data) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def normalize_scalar(value):
    """Convert common textual scalars ('true', '1', 'null') to native values."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if text.lower() in {"null", "none", ""}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return value
