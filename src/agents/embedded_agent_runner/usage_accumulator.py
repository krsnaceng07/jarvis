"""jarvis.agents.embedded_agent_runner.usage_accumulator — per-call token usage accumulation.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/usage-accumulator.ts``.

Public surface:

- :func:`create_usage_accumulator`
- :func:`merge_usage_into_accumulator`
- :func:`to_normalized_usage`
- :func:`to_last_call_usage`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional


# Installable hooks ---------------------------------------------------------

_merge_usage_into_accumulator_hook = None
_to_normalized_usage_hook = None
_to_last_call_usage_hook = None


def set_merge_usage_into_accumulator_hook(fn) -> None:
    global _merge_usage_into_accumulator_hook
    _merge_usage_into_accumulator_hook = fn


def set_to_normalized_usage_hook(fn) -> None:
    global _to_normalized_usage_hook
    _to_normalized_usage_hook = fn


def set_to_last_call_usage_hook(fn) -> None:
    global _to_last_call_usage_hook
    _to_last_call_usage_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_usage_accumulator() -> Dict[str, Any]:
    """Create a fresh usage accumulator with all counters zeroed.

    Mirrors :func:`createUsageAccumulator` (``usage-accumulator.ts``).
    """
    return {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "reasoningTokens": 0,
        "total": 0,
        "lastInput": 0,
        "lastOutput": 0,
        "lastCacheRead": 0,
        "lastCacheWrite": 0,
        "lastContextUsage": None,
        "lastReasoningTokens": 0,
        "lastTotal": 0,
    }


def _has_usage_values(usage: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(usage, dict):
        return False
    candidate_values = [
        usage.get("input"),
        usage.get("output"),
        usage.get("cacheRead"),
        usage.get("cacheWrite"),
        usage.get("reasoningTokens"),
        usage.get("total"),
    ]
    cu = usage.get("contextUsage")
    if isinstance(cu, dict):
        if cu.get("state") == "available":
            candidate_values.append(cu.get("promptTokens"))
            candidate_values.append(cu.get("totalTokens"))
        if cu.get("state") == "unavailable":
            return True
    for v in candidate_values:
        if isinstance(v, (int, float)) and v == v and v not in (float("inf"), float("-inf")) and v > 0:
            return True
    return False


def merge_usage_into_accumulator(
    target: Dict[str, Any], usage: Optional[Dict[str, Any]]
) -> None:
    """Merge a single NormalizedUsage into the running accumulator.

    Mirrors :func:`mergeUsageIntoAccumulator` (``usage-accumulator.ts``).
    """
    if _merge_usage_into_accumulator_hook is not None:
        _merge_usage_into_accumulator_hook(target, usage)
        return
    if not _has_usage_values(usage):
        return
    call_total = usage.get("total")
    if not isinstance(call_total, (int, float)):
        call_total = (
            (usage.get("input") or 0)
            + (usage.get("output") or 0)
            + (usage.get("cacheRead") or 0)
            + (usage.get("cacheWrite") or 0)
        )
    target["input"] = (target.get("input") or 0) + (usage.get("input") or 0)
    target["output"] = (target.get("output") or 0) + (usage.get("output") or 0)
    target["cacheRead"] = (target.get("cacheRead") or 0) + (usage.get("cacheRead") or 0)
    target["cacheWrite"] = (target.get("cacheWrite") or 0) + (usage.get("cacheWrite") or 0)
    target["reasoningTokens"] = (target.get("reasoningTokens") or 0) + (usage.get("reasoningTokens") or 0)
    target["total"] = (target.get("total") or 0) + (call_total or 0)
    target["lastInput"] = usage.get("input") or 0
    target["lastOutput"] = usage.get("output") or 0
    target["lastCacheRead"] = usage.get("cacheRead") or 0
    target["lastCacheWrite"] = usage.get("cacheWrite") or 0
    cu = usage.get("contextUsage")
    target["lastContextUsage"] = copy.deepcopy(cu) if isinstance(cu, dict) else None
    target["lastReasoningTokens"] = usage.get("reasoningTokens") or 0
    target["lastTotal"] = call_total or 0


def to_normalized_usage(usage: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert the accumulator into a NormalizedUsage snapshot (sums).

    Mirrors :func:`toNormalizedUsage` (``usage-accumulator.ts``).
    """
    if _to_normalized_usage_hook is not None:
        v = _to_normalized_usage_hook(usage)
        return v
    has_usage = any(
        (usage.get(k) or 0) > 0
        for k in ("input", "output", "cacheRead", "cacheWrite", "reasoningTokens", "total")
    )
    if not has_usage:
        return None
    out: Dict[str, Any] = {
        "input": usage.get("input") or None,
        "output": usage.get("output") or None,
        "cacheRead": usage.get("cacheRead") or None,
        "cacheWrite": usage.get("cacheWrite") or None,
        "total": usage.get("total") or None,
    }
    if (usage.get("reasoningTokens") or 0) > 0:
        out["reasoningTokens"] = usage["reasoningTokens"]
    return out


def to_last_call_usage(usage: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert the accumulator's `last*` fields into a NormalizedUsage snapshot.

    Mirrors :func:`toLastCallUsage` (``usage-accumulator.ts``).
    """
    if _to_last_call_usage_hook is not None:
        v = _to_last_call_usage_hook(usage)
        return v
    has_usage = any(
        (usage.get(k) or 0) > 0
        for k in (
            "lastInput",
            "lastOutput",
            "lastCacheRead",
            "lastCacheWrite",
            "lastReasoningTokens",
            "lastTotal",
        )
    ) or (usage.get("lastContextUsage") is not None)
    if not has_usage:
        return None
    out: Dict[str, Any] = {
        "input": usage.get("lastInput") or None,
        "output": usage.get("lastOutput") or None,
        "cacheRead": usage.get("lastCacheRead") or None,
        "cacheWrite": usage.get("lastCacheWrite") or None,
        "total": usage.get("lastTotal") or None,
    }
    if usage.get("lastContextUsage") is not None:
        out["contextUsage"] = copy.deepcopy(usage["lastContextUsage"])
    if (usage.get("lastReasoningTokens") or 0) > 0:
        out["reasoningTokens"] = usage["lastReasoningTokens"]
    return out


__all__ = [
    "create_usage_accumulator",
    "merge_usage_into_accumulator",
    "to_normalized_usage",
    "to_last_call_usage",
    "set_merge_usage_into_accumulator_hook",
    "set_to_normalized_usage_hook",
    "set_to_last_call_usage_hook",
]
