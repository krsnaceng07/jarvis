"""jarvis_sdk.memory_host_status_format — memory health status formatters.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/status-format.ts`` (44 LOC).
Three small resolvers that map a feature's enabled + available
flags to a (tone, state/text) pair for status UIs.

Key port decisions:
- TS discriminated union ``"ok" | "warn" | "muted"`` → ``Literal``
  in Python.
- TS return type ``{ tone, state }`` / ``{ tone, text }`` → TypedDict.
- Helper ordering + behavior preserved verbatim.
"""
from __future__ import annotations

from typing import Literal, TypedDict

# Display tone used by memory status renderers. Mirrors OpenClaw's
# ``Tone`` union.
Tone = Literal["ok", "warn", "muted"]


class _VectorStateResult(TypedDict, total=False):
    tone: Tone
    state: Literal["ready", "unavailable", "disabled", "unknown"]


def resolve_memory_vector_state(
    vector: dict,
) -> _VectorStateResult:
    """Resolve vector indexing state from enabled + availability flags.

    Mirrors OpenClaw's ``resolveMemoryVectorState``. When ``enabled``
    is ``False`` → ``disabled`` (muted). When ``available`` is
    ``True`` → ``ready`` (ok). When ``available`` is ``False`` →
    ``unavailable`` (warn). Otherwise → ``unknown`` (muted).
    """
    if not vector.get("enabled"):
        return {"tone": "muted", "state": "disabled"}
    if vector.get("available") is True:
        return {"tone": "ok", "state": "ready"}
    if vector.get("available") is False:
        return {"tone": "warn", "state": "unavailable"}
    return {"tone": "muted", "state": "unknown"}


class _FtsStateResult(TypedDict, total=False):
    tone: Tone
    state: Literal["ready", "unavailable", "disabled"]


def resolve_memory_fts_state(fts: dict) -> _FtsStateResult:
    """Resolve full-text-search state from enabled + availability flags.

    Mirrors OpenClaw's ``resolveMemoryFtsState``. When ``enabled`` is
    ``False`` → ``disabled`` (muted). When ``enabled`` and
    ``available`` → ``ready`` (ok). When ``enabled`` but not
    ``available`` → ``unavailable`` (warn).
    """
    if not fts.get("enabled"):
        return {"tone": "muted", "state": "disabled"}
    return (
        {"tone": "ok", "state": "ready"}
        if fts.get("available")
        else {"tone": "warn", "state": "unavailable"}
    )


class _CacheSummaryResult(TypedDict, total=False):
    tone: Tone
    text: str


def resolve_memory_cache_summary(cache: dict) -> _CacheSummaryResult:
    """Format cache state as concise status text with optional entry count.

    Mirrors OpenClaw's ``resolveMemoryCacheSummary``. When
    ``enabled`` is ``False`` → ``"cache off"`` (muted). When
    ``enabled`` → ``"cache on (N)"`` (ok), where ``N`` is the
    optional ``entries`` count when numeric.
    """
    if not cache.get("enabled"):
        return {"tone": "muted", "text": "cache off"}
    entries = cache.get("entries")
    suffix = f" ({entries})" if isinstance(entries, (int, float)) else ""
    return {"tone": "ok", "text": f"cache on{suffix}"}


__all__ = [
    "Tone",
    "resolve_memory_vector_state",
    "resolve_memory_fts_state",
    "resolve_memory_cache_summary",
]
