"""jarvis.shared.text.tool_call_shaped_text — detect tool-call-shaped text.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/tool-call-shaped-text.ts``.
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional, TypedDict


class ToolCallShapedTextDetection(TypedDict, total=False):
    kind: str  # "json_tool_call" | "xml_tool_call" | "bracketed_tool_call" | "react_action"
    toolName: str


_TOOL_TEXT_PREFILTER_RE = re.compile(
    r"(?:tool[_\s-]?calls?|function[_\s-]?call|"
    r"[\"']"
    r"(?:name|tool_name|function|arguments|args|input|parameters|tool_calls)"
    r"[\"']"
    r"|<\s*tool_call\b|Action\s*:|\[END_TOOL_REQUEST\])",
    re.IGNORECASE,
)
_MAX_SCAN_CHARS = 20_000
_MAX_JSON_CANDIDATES = 20
_MAX_JSON_CANDIDATE_CHARS = 8_000


def _read_tool_name(record: dict) -> Optional[str]:
    for key in ("name", "tool_name", "tool", "function_name"):
        v = record.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _has_tool_args(record: dict) -> bool:
    return any(k in record for k in ("arguments", "args", "input", "parameters"))


def _classify_json_value(value: Any) -> Optional[ToolCallShapedTextDetection]:
    if isinstance(value, list):
        for item in value:
            detection = _classify_json_value(item)
            if detection:
                return detection
        return None
    if not isinstance(value, dict):
        return None
    tool_calls = value.get("tool_calls") or value.get("toolCalls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            detection = _classify_json_value(tc)
            if detection:
                return detection
        return {"kind": "json_tool_call"}
    function_record = value.get("function")
    if isinstance(function_record, dict):
        tool_name = _read_tool_name(function_record)
        if tool_name and _has_tool_args(function_record):
            return {"kind": "json_tool_call", "toolName": tool_name}
    tool_name = _read_tool_name(value)
    if tool_name and _has_tool_args(value):
        return {"kind": "json_tool_call", "toolName": tool_name}
    t = value.get("type")
    type_str = t.strip().lower() if isinstance(t, str) else ""
    if tool_name and type_str in (
        "tool_call",
        "toolcall",
        "tooluse",
        "tool_use",
        "function_call",
        "functioncall",
    ):
        return {"kind": "json_tool_call", "toolName": tool_name}
    return None


_FENCED_JSON_RE = re.compile(
    r"```(?:json|tool|tool_call|function_call)?[^\n\r]*[\r\n]([\s\S]*?)```",
    re.IGNORECASE,
)


def _collect_fenced_json_candidates(text: str) -> List[str]:
    candidates: List[str] = []
    for match in _FENCED_JSON_RE.finditer(text):
        candidate = (match.group(1) or "").strip()
        if candidate and len(candidate) <= _MAX_JSON_CANDIDATE_CHARS:
            candidates.append(candidate)
    return candidates


def _find_balanced_json_end(text: str, start: int) -> Optional[int]:
    opening = text[start]
    closing = "}" if opening == "{" else ("]" if opening == "[" else "")
    if not closing:
        return None
    stack: List[str] = [closing]
    in_string = False
    escaped = False
    for index in range(start + 1, len(text)):
        if index - start > _MAX_JSON_CANDIDATE_CHARS:
            return None
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{" or ch == "[":
            stack.append("}" if ch == "{" else "]")
            continue
        if ch == "}" or ch == "]":
            if not stack or stack[-1] != ch:
                return None
            stack.pop()
            if not stack:
                return index + 1
    return None


def _collect_balanced_json_candidates(text: str) -> List[str]:
    candidates: List[str] = []
    index = 0
    while index < len(text) and len(candidates) < _MAX_JSON_CANDIDATES:
        ch = text[index]
        if ch == "{" or ch == "[":
            end = _find_balanced_json_end(text, index)
            if end is not None:
                candidate = text[index:end].strip()
                if len(candidate) > 1:
                    candidates.append(candidate)
                index = end - 1
        index += 1
    return candidates


def _detect_json_tool_call(text: str) -> Optional[ToolCallShapedTextDetection]:
    candidates = _collect_fenced_json_candidates(text) + _collect_balanced_json_candidates(text)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        detection = _classify_json_value(value)
        if detection:
            return detection
    return None


_XML_TOOL_RE = re.compile(r"<\s*tool_call\b", re.IGNORECASE)
_XML_FUNCTION_RE = re.compile(r"<\s*function=([A-Za-z0-9_.:-]{1,120})\b", re.IGNORECASE)
_XML_NAME_RE = re.compile(r"[\"']name[\"']\s*:\s*[\"']([^\"']{1,120})[\"']", re.IGNORECASE)


def _detect_xml_tool_call(text: str) -> Optional[ToolCallShapedTextDetection]:
    if not _XML_TOOL_RE.search(text):
        return None
    if not _XML_FUNCTION_RE.search(text) and not _XML_NAME_RE.search(text):
        return None
    m = _XML_FUNCTION_RE.search(text)
    tool_name = m.group(1) if m else None
    if not tool_name:
        m = _XML_NAME_RE.search(text)
        if m:
            tool_name = m.group(1).strip() if m.group(1) else None
    out: ToolCallShapedTextDetection = {"kind": "xml_tool_call"}
    if tool_name:
        out["toolName"] = tool_name
    return out


_LEGACY_BRACKETED_RE = re.compile(
    r"\[\s*TOOL_CALL\s*\]\s*\{[\s\S]{0,8000}?\btool\s*=>\s*[\"']([A-Za-z_][A-Za-z0-9_.:-]{0,119})[\"'][\s\S]{0,8000}?\bargs\s*=>[\s\S]*?(?:\[\s*\/\s*TOOL_CALL\s*\]|$)",
    re.IGNORECASE,
)
_BRACKETED_RE = re.compile(
    r"^\s*\[([A-Za-z_][A-Za-z0-9_.:-]{0,119})\]\s+[\s\S]*?\[END_TOOL_REQUEST\]\s*$",
    re.IGNORECASE,
)


def _detect_bracketed_tool_call(text: str) -> Optional[ToolCallShapedTextDetection]:
    m = _LEGACY_BRACKETED_RE.search(text)
    if m and m.group(1):
        return {"kind": "bracketed_tool_call", "toolName": m.group(1)}
    m = _BRACKETED_RE.match(text)
    if m and m.group(1):
        return {"kind": "bracketed_tool_call", "toolName": m.group(1)}
    return None


_REACT_ACTION_RE = re.compile(
    r"(?:^|\n)\s*Action\s*:\s*([A-Za-z_][A-Za-z0-9_.:-]{0,119})\s*(?:\r?\n)+\s*Action Input\s*:",
    re.IGNORECASE,
)


def _detect_react_action(text: str) -> Optional[ToolCallShapedTextDetection]:
    m = _REACT_ACTION_RE.search(text)
    if not m or not m.group(1):
        return None
    return {"kind": "react_action", "toolName": m.group(1)}


def detect_tool_call_shaped_text(text: str) -> Optional[ToolCallShapedTextDetection]:
    """Detect assistant-visible text that looks like an unexecuted tool call.

    Mirrors :func:`detectToolCallShapedText`
    (``shared/text/tool-call-shaped-text.ts``).
    """
    if not isinstance(text, str):
        return None
    trimmed = text[:_MAX_SCAN_CHARS].strip()
    if not trimmed or not _TOOL_TEXT_PREFILTER_RE.search(trimmed):
        return None
    return (
        _detect_bracketed_tool_call(trimmed)
        or _detect_xml_tool_call(trimmed)
        or _detect_json_tool_call(trimmed)
        or _detect_react_action(trimmed)
    )


__all__ = ["ToolCallShapedTextDetection", "detect_tool_call_shaped_text"]
