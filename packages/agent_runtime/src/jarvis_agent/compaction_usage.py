"""Stale assistant usage cleanup after transcript compaction.

Port of ``src/agents/compaction-usage.ts``.

After a compaction entry is written to the transcript, assistant ``usage``
snapshots that predate it reflect a context window that no longer exists.
Keeping them would cause the session runtime to over-count tokens.  This
module zeroes those snapshots while preserving their structural validity —
the session runtime needs the ``usage`` field to remain present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import AgentMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_compaction_usage_timestamp(value: Any) -> float | None:
    """Parse a timestamp value from a message to a numeric ms epoch.

    Parity: ``parseCompactionUsageTimestamp``.
    """
    if isinstance(value, (int, float)) and _is_finite(value):
        return float(value)
    if isinstance(value, str):
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.timestamp() * 1000
        except (ValueError, AttributeError):
            pass
        try:
            numeric = float(value)
            if _is_finite(numeric):
                return numeric
        except ValueError:
            pass
    return None


def _is_finite(value: float) -> bool:
    import math

    return math.isfinite(value)


def _make_zero_usage() -> Any:
    """Return a zero-valued usage snapshot that keeps the usage field valid.

    Parity: ``makeZeroUsageSnapshot``.
    Delegates to ``jarvis_llm.Usage`` when available; falls back to a plain
    ``dict`` so this module stays importable without ``jarvis_llm``.
    """
    try:
        from jarvis_llm import Cost, Usage

        zero_cost = Cost(input=0, output=0, cache_read=0, cache_write=0, total=0)
        return Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            context_usage=None,
            total_tokens=0,
            cost=zero_cost,
        )
    except Exception:
        return {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
            "context_usage": None,
            "total_tokens": 0,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def strip_stale_assistant_usage_before_latest_compaction(
    messages: "list[AgentMessage]",
    *,
    mutate: bool = False,
    when_missing_compaction_summary: str = "preserve",
) -> "list[AgentMessage]":
    """Zero assistant usage snapshots invalidated by the latest compaction.

    After a ``compactionSummary`` role entry is written, every assistant
    message that was part of the summarized history carries a stale usage
    snapshot.  Keeping them intact would inflate token accounting for the
    next turn.  This function replaces stale ``usage`` fields with a
    structurally valid zero snapshot.

    Parity: ``stripStaleAssistantUsageBeforeLatestCompaction``.

    Args:
        messages: Full ordered message list (including the compaction entry).
        mutate: When ``True``, modify the list in-place instead of copying.
        when_missing_compaction_summary: ``"preserve"`` (default) — do nothing
            when no compaction entry exists; ``"zeroAssistantUsage"`` — zero all
            assistant usage even without a compaction entry (used during
            session repair).

    Returns:
        The (possibly mutated) message list with stale usage zeroed.
    """
    latest_compaction_index = -1
    latest_compaction_timestamp: float | None = None

    for i, entry in enumerate(messages):
        if getattr(entry, "role", None) != "compactionSummary":
            continue
        latest_compaction_index = i
        ts = getattr(entry, "timestamp", None)
        latest_compaction_timestamp = _parse_compaction_usage_timestamp(ts)

    has_compaction_summary = latest_compaction_index != -1

    if not has_compaction_summary and when_missing_compaction_summary != "zeroAssistantUsage":
        return messages

    out = messages if mutate else list(messages)
    touched = False

    for i, candidate in enumerate(out):
        if getattr(candidate, "role", None) != "assistant":
            continue
        usage = getattr(candidate, "usage", None)
        if usage is None or not hasattr(usage, "__dict__") and not isinstance(usage, dict):
            continue

        msg_timestamp = _parse_compaction_usage_timestamp(getattr(candidate, "timestamp", None))
        compaction_timestamp = latest_compaction_timestamp
        has_timestamp_boundary = (
            has_compaction_summary
            and compaction_timestamp is not None
            and msg_timestamp is not None
        )

        stale_by_missing_summary = not has_compaction_summary
        stale_by_timestamp = (
            has_timestamp_boundary and msg_timestamp <= compaction_timestamp  # type: ignore[operator]
        )
        stale_by_legacy_ordering = (
            has_compaction_summary and not has_timestamp_boundary and i < latest_compaction_index
        )

        if not (stale_by_missing_summary or stale_by_timestamp or stale_by_legacy_ordering):
            continue

        # Keep usage structurally valid; only zero the values.
        try:
            import dataclasses

            if dataclasses.is_dataclass(candidate):
                out[i] = dataclasses.replace(candidate, usage=_make_zero_usage())  # type: ignore[arg-type]
                touched = True
                continue
        except Exception:
            pass

        # Dict-style message fallback.
        try:
            out[i] = {**candidate, "usage": _make_zero_usage()}  # type: ignore[assignment]
            touched = True
        except Exception:
            pass

    return out if touched else messages


__all__ = [
    "strip_stale_assistant_usage_before_latest_compaction",
]
