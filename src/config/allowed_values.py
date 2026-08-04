"""jarvis.config.allowed_values — allowed-value hint formatter for config validation.

OpenClaw parity: mirrors ``openclaw-main/src/config/allowed-values.ts``.
"""
from __future__ import annotations

import json
from typing import Any, List, Optional, TypedDict

MAX_ALLOWED_VALUES_HINT = 12
MAX_ALLOWED_VALUE_CHARS = 160


class AllowedValuesSummary(TypedDict, total=False):
    values: List[str]
    hiddenCount: int
    formatted: str


def _truncate_hint_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... (+{len(text) - limit} chars)"


def _safe_stringify(value: Any) -> str:
    if value is None:
        return ""
    try:
        s = json.dumps(value)
        if s is not None:
            return s
    except (TypeError, ValueError):
        pass
    return str(value)


def _to_allowed_value_label(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(_truncate_hint_text(value, MAX_ALLOWED_VALUE_CHARS))
    return _truncate_hint_text(_safe_stringify(value), MAX_ALLOWED_VALUE_CHARS)


def _to_allowed_value_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _safe_stringify(value)


def _to_allowed_value_dedup_key(value: Any) -> str:
    if value is None:
        return "null:null"
    kind = type(value).__name__
    if isinstance(value, str):
        return f"string:{value}"
    return f"{kind}:{_safe_stringify(value)}"


def summarize_allowed_values(values: List[Any]) -> Optional[AllowedValuesSummary]:
    """Summarize enum/allowed-value candidates for compact validation error hints.

    Mirrors :func:`summarizeAllowedValues`
    (``shared/config/allowed-values.ts``).
    """
    if not values:
        return None
    deduped: List[dict] = []
    seen: set = set()
    for item in values:
        key = _to_allowed_value_dedup_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({
            "value": _to_allowed_value_value(item),
            "label": _to_allowed_value_label(item),
        })
    shown = deduped[:MAX_ALLOWED_VALUES_HINT]
    hidden_count = len(deduped) - len(shown)
    formatted_core = ", ".join(entry["label"] for entry in shown)
    formatted = (
        f"{formatted_core}, ... (+{hidden_count} more)"
        if hidden_count > 0
        else formatted_core
    )
    return {
        "values": [entry["value"] for entry in shown],
        "hiddenCount": hidden_count,
        "formatted": formatted,
    }


def _message_already_includes_allowed_values(message: str) -> bool:
    lower = message.lower()
    return "(allowed:" in lower or "expected one of" in lower


def append_allowed_values_hint(message: str, summary: AllowedValuesSummary) -> str:
    """Append an allowed-values hint unless the validation message already includes one.

    Mirrors :func:`appendAllowedValuesHint`
    (``shared/config/allowed-values.ts``).
    """
    if _message_already_includes_allowed_values(message):
        return message
    return f"{message} (allowed: {summary['formatted']})"


__all__ = [
    "MAX_ALLOWED_VALUES_HINT",
    "MAX_ALLOWED_VALUE_CHARS",
    "AllowedValuesSummary",
    "summarize_allowed_values",
    "append_allowed_values_hint",
]
