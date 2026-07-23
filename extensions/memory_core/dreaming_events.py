"""memory_core.dreaming_events — structured event helpers for the dreaming pipeline.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-events.ts``
(32 LOC). Provides a single helper:

- ``append_failed_dreaming_event`` — appends a ``memory.dream.completed``
  event with ``outcome: "failed"`` to the host's memory-host event log.
  The host swallows write errors and emits a warning (the event log is
  best-effort diagnostic, not a critical path).
"""
from __future__ import annotations

from typing import Literal

from .dreaming_shared import format_error_message
from .time import resolve_memory_core_now_ms, resolve_memory_core_timestamp


# Mirrors OpenClaw's ``MemoryDreamingPhaseName`` literal type. The
# value is the same string the host uses to tag the event so consumers
# can filter by phase.
MemoryDreamingPhaseName = Literal["light", "rem", "deep", "shadow-trial"]
MemoryDreamingStorageMode = Literal["inline", "separate", "both"]


# Module-level logger type — matches the OpenClaw's subset of the host
# logger interface we need (just ``warn``).
class _WarnLogger:
    def warn(self, message: str) -> None: ...


def append_failed_dreaming_event(
    workspace_dir: str,
    phase: MemoryDreamingPhaseName,
    error: str,
    storage_mode: MemoryDreamingStorageMode,
    now_ms: int | float | None = None,
    logger: _WarnLogger | None = None,
) -> None:
    """Append a ``memory.dream.completed`` event with ``outcome: "failed"``.

    Mirrors OpenClaw's ``appendFailedDreamingEvent``. Best-effort: write
    errors are caught and logged via ``logger.warn``. The event log lives
    at ``<workspace>/.jarvis/memory/events.jsonl`` (host-defined path).
    """
    # Lazy import to avoid a hard dependency on the memory_host_sdk at
    # module import time (matches OpenClaw's TS import pattern).
    try:
        from jarvis_sdk.memory_host_events import append_memory_host_event  # type: ignore[attr-defined]
    except ImportError:
        # SDK doesn't expose the events API yet — degrade to a
        # no-op + warning so the dreaming pipeline can still run.
        if logger is not None:
            logger.warn(
                f"memory-core: cannot write {phase} dreaming outcome event "
                f"(jarvis_sdk.memory_host_events not available)"
            )
        return

    try:
        append_memory_host_event(
            workspace_dir,
            {
                "type": "memory.dream.completed",
                "timestamp": resolve_memory_core_timestamp(
                    resolve_memory_core_now_ms(now_ms)
                ),
                "phase": phase,
                "outcome": "failed",
                "error": error,
                "lineCount": 0,
                "storageMode": storage_mode,
            },
        )
    except Exception as exc:
        if logger is not None:
            logger.warn(
                f"memory-core: failed to write {phase} dreaming outcome event "
                f"for workspace {workspace_dir}: {format_error_message(exc)}"
            )


__all__ = [
    "MemoryDreamingPhaseName",
    "MemoryDreamingStorageMode",
    "append_failed_dreaming_event",
]
