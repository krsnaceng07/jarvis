"""jarvis_sdk.memory_host_events — public event helpers for memory host.

OpenClaw parity: mirrors ``src/memory-host-sdk/events.ts`` (83 LOC).
Provides the high-level helpers for appending + reading memory host
events. Re-exports the event types from ``memory_host_event_types``.

The actual storage is delegated to ``memory_host_event_store``. This
module exists so plugin + host code can import a single, stable path
instead of reaching into individual store functions.

Key port decisions:
- ``append_memory_host_event`` mirrors the TS async function: calls
  ``register_memory_host_event`` from the store module. In OpenClaw
  the store is sync; we keep it sync in the port and the async
  signature is preserved for compatibility.
- The legacy JSONL path (``MEMORY_HOST_EVENT_LOG_RELATIVE_PATH``) is
  retained as a constant for doctor migration discovery — no
  runtime read/write (OpenClaw migrated the live data to SQLite
  plugin state; the JSONL file is a discovery-only artifact).
- Read helpers filter out the opt-in diagnostic variant
  (``memory.recall.skipped``) for the public read surface; the
  ``read_memory_host_event_records`` variant includes them.
"""
from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, TypeVar, cast

_T = TypeVar("_T")

# Re-export the event types from the dedicated module so callers can
# import them from this single path. Mirrors OpenClaw's barrel
# re-export pattern.
from .memory_host_event_types import (
    MemoryDreamOutcome,
    MemoryHostDreamCompletedEvent,
    MemoryHostEvent,
    MemoryHostEventRecord,
    MemoryHostPromotionAppliedEvent,
    MemoryHostRecallRecordedEvent,
    MemoryHostRecallSkippedEvent,
)

# The store module provides the sync SQLite-backed register/list API.
# The TS source imports from ``./event-store.js`` directly; we port
# the implementation to ``memory_host_event_store.py`` and import
# from there.
from .memory_host_event_store import (
    StoredMemoryHostEvent,
    list_stored_memory_host_events,
    normalize_memory_host_event_record_for_storage,
    register_memory_host_event,
)


# Re-export the normalize helper for callers that want to validate
# before storing. (The OpenClaw source re-exports it from this
# module; the actual implementation lives in event-store.ts.)
__all__ = [
    # Constants
    "MEMORY_HOST_EVENT_LOG_RELATIVE_PATH",
    # Type re-exports
    "MemoryDreamOutcome",
    "MemoryHostDreamCompletedEvent",
    "MemoryHostEvent",
    "MemoryHostEventRecord",
    "MemoryHostPromotionAppliedEvent",
    "MemoryHostRecallRecordedEvent",
    "MemoryHostRecallSkippedEvent",
    # Re-exported helper
    "normalize_memory_host_event_record_for_storage",
    # Public API
    "resolve_memory_host_event_log_path",
    "append_memory_host_event",
    "read_memory_host_events",
    "read_memory_host_event_records",
]


# ── Legacy JSONL path (doctor migration discovery only) ─────────────


#: Legacy workspace JSONL path retained only for doctor migration
#: discovery. Mirrors OpenClaw's ``MEMORY_HOST_EVENT_LOG_RELATIVE_PATH``.
MEMORY_HOST_EVENT_LOG_RELATIVE_PATH = os.path.join("memory", ".dreams", "events.jsonl")


def resolve_memory_host_event_log_path(workspace_dir: str) -> str:
    """Resolve the retired JSONL source path without reading it.

    Mirrors OpenClaw's ``resolveMemoryHostEventLogPath``. Returns the
    absolute path to the legacy JSONL log file (used by the doctor
    migration harness to discover pre-SQLite workspaces).
    """
    return os.path.join(workspace_dir, MEMORY_HOST_EVENT_LOG_RELATIVE_PATH)


# ── Public API ────────────────────────────────────────────────────────


def _apply_memory_host_event_limit(
    events: Sequence[_T], limit: int | None
) -> list[_T]:
    """Apply a tail-limit to a list of events.

    Mirrors OpenClaw's ``applyMemoryHostEventLimit``: when
    ``limit`` is missing, returns the full list; when ``limit`` is
    0, returns ``[]``; otherwise slices the last ``limit`` items.
    """
    if limit is None:
        return list(events)
    if not isinstance(limit, (int, float)) or limit != limit:  # NaN
        return list(events)
    normalized = max(0, int(limit))
    return list(events[-normalized:]) if normalized > 0 else []


async def append_memory_host_event(
    workspace_dir: str,
    event: MemoryHostEventRecord,
    *,
    env: dict[str, Any] | None = None,
) -> None:
    """Append one memory host event to shared SQLite plugin state.

    Mirrors OpenClaw's ``appendMemoryHostEvent``. The async
    signature is preserved for OpenClaw parity; the underlying
    store call is sync (matches the in-process SQLite state).
    """
    register_memory_host_event(workspace_dir=workspace_dir, event=event, env=env)


def _read_memory_host_event_records_raw(
    workspace_dir: str,
    limit: int | None = None,
    env: dict[str, Any] | None = None,
) -> list[MemoryHostEventRecord]:
    """Read recent memory host event records, with no filtering.

    Mirrors OpenClaw's internal ``readMemoryHostEventRecordsRaw``.
    """
    entries = list_stored_memory_host_events(
        workspace_dir=workspace_dir, limit=limit, env=env
    )
    # ``entries`` is a list of PersistedMemoryHostEvent-shaped dicts;
    # extract the inner ``event`` field and preserve the declared
    # MemoryHostEventRecord payload shape.
    return [cast(StoredMemoryHostEvent, entry["value"])["event"] for entry in entries]


async def read_memory_host_events(
    workspace_dir: str,
    *,
    limit: int | None = None,
    env: dict[str, Any] | None = None,
) -> list[MemoryHostEvent]:
    """Read recent memory host events, excluding opt-in diagnostic variants.

    Mirrors OpenClaw's ``readMemoryHostEvents``. Filters out
    ``memory.recall.skipped`` events (the opt-in diagnostic variant)
    before applying the limit.
    """
    raw = _read_memory_host_event_records_raw(workspace_dir, limit=None, env=env)
    legacy: list[MemoryHostEvent] = [
        cast(MemoryHostEvent, e)
        for e in raw
        if e.get("type") != "memory.recall.skipped"
    ]
    return _apply_memory_host_event_limit(legacy, limit)


async def read_memory_host_event_records(
    workspace_dir: str,
    *,
    limit: int | None = None,
    env: dict[str, Any] | None = None,
) -> list[MemoryHostEventRecord]:
    """Read recent memory host event records, including diagnostic variants.

    Mirrors OpenClaw's ``readMemoryHostEventRecords``. No filtering
    is applied — callers that don't want diagnostic variants should
    use ``read_memory_host_events`` instead.
    """
    raw = _read_memory_host_event_records_raw(workspace_dir, limit=None, env=env)
    return _apply_memory_host_event_limit(raw, limit)
