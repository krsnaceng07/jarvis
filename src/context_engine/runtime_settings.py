"""Normalization for the runtime-settings snapshot handed to context engines.

OpenClaw parity: ``src/context-engine/runtime-settings.ts``.
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["build_context_engine_runtime_settings"]

_RUNTIME_REASON_CODES = {
    "provider_timeout",
    "provider_unavailable",
    "rate_limited",
    "context_overflow",
    "runtime_unavailable",
    "unknown",
}


def _normalize_nullable_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _normalize_nullable_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _normalize_reason_code(value: Any) -> str | None:
    normalized = _normalize_nullable_string(value)
    if not normalized:
        return None
    if normalized in _RUNTIME_REASON_CODES:
        return normalized

    lower = normalized.lower()
    if "timeout" in lower:
        return "provider_timeout"
    if "rate" in lower or "limit" in lower or "429" in lower:
        return "rate_limited"
    if "overflow" in lower or "context" in lower or "pressure" in lower:
        return "context_overflow"
    if "runtime" in lower:
        return "runtime_unavailable"
    if "provider" in lower or "primary" in lower or "unavailable" in lower:
        return "provider_unavailable"
    return "unknown"


def build_context_engine_runtime_settings(params: Mapping[str, Any]) -> dict[str, Any]:
    """Build the schema-versioned runtime settings snapshot for one run.

    ``params`` mirrors the TS options object (camelCase keys):
    ``mode``, ``harnessId``, ``runtimeId``, ``requestedModel``,
    ``resolvedModel``, ``provider``, ``modelFamily``,
    ``selectedContextEngineId``, ``contextEngineSelectionSource``,
    ``fallbackReason``, ``degradedReason``, ``promptTokenBudget``,
    ``maxOutputTokens``, and the required ``contextEngineHost``.
    """
    host = params["contextEngineHost"]
    host_id = _normalize_nullable_string(host.get("id"))
    selected_id = _normalize_nullable_string(params.get("selectedContextEngineId"))
    selection_source = params.get("contextEngineSelectionSource") or (
        "configured" if selected_id else "unknown"
    )

    requested_model = _normalize_nullable_string(params.get("requestedModel"))
    resolved_model = _normalize_nullable_string(params.get("resolvedModel"))
    fallback_reason = _normalize_reason_code(params.get("fallbackReason"))
    degraded_reason = _normalize_reason_code(params.get("degradedReason"))
    resolved_via_fallback = (
        requested_model is not None
        and resolved_model is not None
        and requested_model != resolved_model
    )
    mode = params.get("mode") or (
        "degraded"
        if degraded_reason
        else "fallback"
        if fallback_reason or resolved_via_fallback
        else "normal"
    )

    return {
        "schemaVersion": 1,
        "runtime": {
            "host": "openclaw",
            "mode": mode,
            "harnessId": _normalize_nullable_string(params.get("harnessId")),
            "runtimeId": _normalize_nullable_string(params.get("runtimeId")),
        },
        "model": {
            "requested": requested_model,
            "resolved": resolved_model,
            "provider": _normalize_nullable_string(params.get("provider")),
            "family": _normalize_nullable_string(params.get("modelFamily")),
        },
        "contextEngineSelection": {
            "selectedId": selected_id,
            "source": selection_source,
        },
        "executionHost": {
            "id": host_id,
            "label": _normalize_nullable_string(host.get("label")),
        },
        "limits": {
            "promptTokenBudget": _normalize_nullable_number(
                params.get("promptTokenBudget")
            ),
            "maxOutputTokens": _normalize_nullable_number(params.get("maxOutputTokens")),
        },
        "diagnostics": {
            "fallbackReason": fallback_reason,
            "degradedReason": degraded_reason,
        },
    }
