"""jarvis.utils.transcript_tools — transcript inspection helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/transcript-tools.ts``.

Public surface:

- :func:`extract_tool_call_names`
- :func:`has_tool_call`
- :func:`count_tool_results`
"""
from __future__ import annotations

from typing import Any, Dict, List


#: Transcript block types that represent a tool call.
_TOOL_CALL_TYPES = frozenset({"tool_use", "toolcall", "tool_call"})

#: Transcript block types that represent a tool result.
_TOOL_RESULT_TYPES = frozenset({"tool_result", "tool_result_error"})


def _normalize_optional_string(value: Any) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or ""
    return ""


def _normalize_lower(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def extract_tool_call_names(message: Dict[str, Any]) -> List[str]:
    """Extract de-duplicated tool names from a transcript message.

    Mirrors :func:`extractToolCallNames` (``utils/transcript-tools.ts``).
    """
    names: List[str] = []
    seen: set = set()
    tool_name = _normalize_optional_string(message.get("toolName") or message.get("tool_name"))
    if tool_name and tool_name not in seen:
        seen.add(tool_name)
        names.append(tool_name)
    content = message.get("content")
    if not isinstance(content, list):
        return names
    for entry in content:
        if not isinstance(entry, dict):
            continue
        if _normalize_lower(entry.get("type")) not in _TOOL_CALL_TYPES:
            continue
        name = _normalize_optional_string(entry.get("name"))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def has_tool_call(message: Dict[str, Any]) -> bool:
    """Whether ``message`` contains any recognized tool-call marker.

    Mirrors :func:`hasToolCall` (``utils/transcript-tools.ts``).
    """
    return bool(extract_tool_call_names(message))


def count_tool_results(message: Dict[str, Any]) -> Dict[str, int]:
    """Count recognized tool-result blocks (and the subset marked as errors).

    Mirrors :func:`countToolResults` (``utils/transcript-tools.ts``).
    """
    total = 0
    errors = 0
    content = message.get("content")
    if not isinstance(content, list):
        return {"total": 0, "errors": 0}
    for entry in content:
        if not isinstance(entry, dict):
            continue
        if _normalize_lower(entry.get("type")) not in _TOOL_RESULT_TYPES:
            continue
        total += 1
        if entry.get("is_error") is True:
            errors += 1
    return {"total": total, "errors": errors}


__all__ = [
    "extract_tool_call_names",
    "has_tool_call",
    "count_tool_results",
]
