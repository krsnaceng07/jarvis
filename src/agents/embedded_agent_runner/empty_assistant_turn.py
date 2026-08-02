"""jarvis.agents.embedded_agent_runner.empty_assistant_turn — empty-turn detection.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/empty-assistant-turn.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`is_zero_usage_empty_stop_assistant_turn` —
  detect provider stop turns that
  contain no assistant-visible
  content.

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Optional


def _as_finite_number(value: Any) -> Optional[int]:
    """Coerce ``value`` to a finite
    number, or ``None`` if it isn't.
    Mirrors :func:`asFiniteNumber`
    from
    ``@openclaw/normalization-core/number-coercion``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None


def _has_zero_token_usage_snapshot(usage: Any) -> bool:
    """Check if ``usage`` is a
    zero-token usage snapshot.
    Mirrors
    :func:`hasZeroTokenUsageSnapshot`
    (``empty-assistant-turn.ts:32-52``)."""
    if not usage or not isinstance(usage, dict):
        return False
    input_ = _as_finite_number(usage.get("input"))
    output = _as_finite_number(usage.get("output"))
    cache_read = _as_finite_number(usage.get("cacheRead"))
    cache_write = _as_finite_number(usage.get("cacheWrite"))
    total = _as_finite_number(
        usage.get("total")
        if "total" in usage
        else usage.get("totalTokens")
        if "totalTokens" in usage
        else usage.get("total_tokens")
    )
    if total is not None:
        return total == 0 and all(
            v is None or v == 0
            for v in (input_, output, cache_read, cache_write)
        )
    components = [
        v
        for v in (input_, output, cache_read, cache_write)
        if v is not None
    ]
    return bool(components) and all(v == 0 for v in components)


def is_zero_usage_empty_stop_assistant_turn(
    message: Any,
) -> bool:
    """Detect provider stop turns that
    contain no assistant-visible
    content. Mirrors
    :func:`isZeroUsageEmptyStopAssistantTurn`
    (``empty-assistant-turn.ts:54-61``)."""
    if not message or not isinstance(message, dict):
        return False
    return bool(
        message.get("stopReason") == "stop"
        and isinstance(message.get("content"), list)
        and len(message.get("content", [])) == 0
        and _has_zero_token_usage_snapshot(message.get("usage"))
    )


__all__ = ["is_zero_usage_empty_stop_assistant_turn"]
