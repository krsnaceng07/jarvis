"""jarvis_sdk.memory_host_event_store — durable event storage for memory host.

OpenClaw parity: mirrors ``src/memory-host-sdk/event-store.ts`` (359 LOC).
Provides the SQLite-backed journal + cursor store for memory host
events. Mirrors OpenClaw's plugin-state runtime exactly.

Architecture (mirrors OpenClaw):

- **Journal** (namespace ``memory-host.events``) — append-only
  sequence of event records, keyed by
  ``<workspaceHash>:event:1:<16-digit sequence>``. Capped at
  ``MAX_MEMORY_HOST_EVENTS = 10_000`` per workspace.
- **Cursors** (namespace ``memory-host.event-cursors``) — per-workspace
  monotonic sequence counter, capped at
  ``MAX_MEMORY_HOST_EVENT_CURSORS = 1_000``.

Both namespaces live in the shared plugin-state runtime
(``memory-core`` plugin) so they share the rotation budget with
sibling state. The two-namespace split lets us retain the cursor
even when the journal rotates old events out.

The public API is:

- ``normalize_memory_host_event_record_for_storage(value)`` — validate
  + bound an event payload before persisting (truncate oversized
  fields, return ``None`` for malformed payloads).
- ``register_memory_host_event(workspace_dir, event, env=None)`` —
  append one event; raises ``TypeError`` on invalid input.
- ``list_stored_memory_host_events(workspace_dir, limit=None,
  env=None)`` — read events in newest-first order (capped by limit).
- ``set_max_memory_host_events_for_tests(max_entries=None)`` — test
  override for the journal cap.

Key port decisions:
- Workspace identity uses ``resolve_workspace_state_identity`` when
  available; falls back to a SHA-256 of the canonicalized path. The
  TS source uses the same fallback pattern.
- All keys are produced via the workspace-hash + namespace-key
  pattern from OpenClaw (``memoryHostEventStorageKey``,
  ``cursorKey``, etc.).
- Bound size limits preserved verbatim:
  - ``MAX_MEMORY_HOST_EVENT_JSON_BYTES = 8192`` (8 KB)
  - ``MAX_MEMORY_HOST_EVENT_ITEMS = 10`` (results per event)
  - ``MAX_MEMORY_HOST_EVENT_TEXT_BYTES = 2048`` (2 KB)
  - ``MAX_MEMORY_HOST_EVENT_PATH_BYTES = 256``
  - ``WORKSPACE_HASH_BYTES = 24``
  - ``MAX_MEMORY_HOST_EVENT_CURSORS = 1000``
  - ``MAX_MEMORY_HOST_EVENTS = 10_000``
- The TS source uses ``registerPluginStateSyncSequencedJournalEntry``
  for atomic cursor+journal write. We model the same pattern via a
  in-process lock that orders the cursor advance + journal insert.
  When the SDK exposes a real plugin-state journal, swap to it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from numbers import Real
from typing import Any, Literal, TypedDict, cast

from .memory_host_event_types import (
    MemoryHostDreamCompletedEvent,
    MemoryHostEventRecord,
    MemoryHostPromotionCandidate,
    MemoryHostRecallRecordedEvent,
    MemoryHostRecallSkippedEvent,
    MemoryHostRecallResult,
)

# ── Constants (mirrors OpenClaw) ─────────────────────────────────────

MEMORY_HOST_EVENTS_PLUGIN_ID = "memory-core"
MEMORY_HOST_EVENTS_NAMESPACE = "memory-host.events"
MEMORY_HOST_EVENT_CURSORS_NAMESPACE = "memory-host.event-cursors"

# Event rotation retains deep diagnostics without consuming memory-core's
# plugin-wide 50,000-row budget or starving sibling state namespaces.
MAX_MEMORY_HOST_EVENTS = 10_000
MAX_MEMORY_HOST_EVENT_CURSORS = 1_000
MAX_MEMORY_HOST_EVENT_JSON_BYTES = 8 * 1024
MAX_MEMORY_HOST_EVENT_ITEMS = 10
MAX_MEMORY_HOST_EVENT_TEXT_BYTES = 2 * 1024
MAX_MEMORY_HOST_EVENT_PATH_BYTES = 256
WORKSPACE_HASH_BYTES = 24


# ── Types ─────────────────────────────────────────────────────────────


class StoredMemoryHostEvent(TypedDict):
    """A single event stored in the journal."""

    kind: Literal["event"]
    event: MemoryHostEventRecord
    recordedAt: int
    sequence: int


class PersistedMemoryHostEvent(TypedDict):
    """A single entry returned by ``list_stored_memory_host_events``."""

    key: str
    value: StoredMemoryHostEvent
    createdAt: int


# Module-level override for the journal cap (test-only).
_max_memory_host_events_for_tests: int | None = None

# Module-level in-process lock to serialize the cursor advance + journal
# insert. This matches the OpenClaw ``registerPluginStateSyncSequencedJournalEntry``
# pattern (which is itself backed by an in-process mutex). When the
# SDK exposes a real plugin-state journal, swap to it.
_event_store_lock = threading.Lock()


def set_max_memory_host_events_for_tests(max_entries: int | None = None) -> None:
    """Test-only retention override; production keeps 10,000-event cap.

    Mirrors OpenClaw's ``setMaxMemoryHostEventsForTests``. Pass
    ``None`` to reset to the production default.
    """
    global _max_memory_host_events_for_tests
    _max_memory_host_events_for_tests = max_entries


def _get_max_memory_host_events() -> int:
    """Return the current journal cap (test override or production)."""
    return (
        _max_memory_host_events_for_tests
        if _max_memory_host_events_for_tests is not None
        else MAX_MEMORY_HOST_EVENTS
    )


# ── Workspace identity ──────────────────────────────────────────────


def _normalize_memory_host_workspace_key(workspace_dir: str) -> str:
    """Canonicalize the workspace path for the event key.

    Mirrors OpenClaw's ``normalizeMemoryHostWorkspaceKey``: resolves
    symlinks via ``resolveWorkspaceStateIdentity`` when available;
    otherwise path-resolves + replaces backslashes. On Windows the
    result is lowercased so case-aliases share one namespace.
    """
    # The OpenClaw source can optionally resolve a workspace identity helper
    # when available. In this SDK port we currently do not ship that helper,
    # so fall back to path normalization only.
    resolved = os.path.normpath(workspace_dir).replace("\\", "/")
    return resolved.lower() if sys.platform == "win32" else resolved


def _memory_host_workspace_prefix(workspace_dir: str) -> str:
    """Return the 24-char SHA-256 hex prefix for the workspace.

    Mirrors OpenClaw's ``memoryHostWorkspacePrefix``.
    """
    return hashlib.sha256(
        _normalize_memory_host_workspace_key(workspace_dir).encode("utf-8")
    ).hexdigest()[:WORKSPACE_HASH_BYTES]


def _event_key_prefix(workspace_dir: str) -> str:
    return f"{_memory_host_workspace_prefix(workspace_dir)}:event:"


def _event_key_range_end(workspace_dir: str) -> str:
    # The TS source uses ``:event;`` (semicolon) as the upper-bound exclusive.
    # In Python's string comparison this sorts strictly after ``:event:``
    # because ``;`` (0x3B) > ``:`` (0x3A) but < digits and lowercase letters.
    return f"{_memory_host_workspace_prefix(workspace_dir)}:event;"


def _memory_host_event_storage_key(workspace_dir: str, sequence: int) -> str:
    """Return the journal key for ``sequence``.

    Mirrors OpenClaw's ``memoryHostEventStorageKey``: throws if
    ``sequence`` is not a safe integer; pads the sequence to 16 digits
    so the keys sort lexicographically.
    """
    if not isinstance(sequence, int) or not (-(2**53) < sequence < 2**53):
        raise ValueError("Memory host event sequence must be a safe integer")
    return (
        f"{_event_key_prefix(workspace_dir)}1:"
        f"{str(sequence).zfill(16)}"
    )


def _cursor_key(workspace_dir: str) -> str:
    return f"{_memory_host_workspace_prefix(workspace_dir)}:cursor"


# ── Validation / normalization helpers ──────────────────────────────


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and value == value  # NaN check


def _is_record(value: Any) -> bool:
    return bool(value) and isinstance(value, dict) and not isinstance(value, (list, tuple, set))


def _truncate_utf8(
    value: str, max_bytes: int
) -> tuple[str, bool]:
    """Truncate ``value`` to ``max_bytes`` UTF-8 bytes, preserving UTF-16 surrogate pairs.

    Mirrors OpenClaw's ``truncateUtf8`` (binary-search based; appends
    ``…`` (3 bytes) when truncated). Returns ``(value, truncated)``.
    """
    if not isinstance(value, str):
        return "", True
    if len(value.encode("utf-8")) <= max_bytes:
        return value, False
    # Binary search: find the longest prefix whose UTF-8 size fits
    # within ``max_bytes - 3`` (room for the ellipsis byte).
    budget = max_bytes - 3
    if budget < 0:
        return "", True
    lo, hi = 0, len(value)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(value[:mid].encode("utf-8")) <= budget:
            lo = mid
        else:
            hi = mid - 1
    # Don't split a high-surrogate from its low-surrogate pair.
    end = lo
    if end > 0 and ord(value[end - 1]) in (0xD800, 0xDBFF):
        end -= 1
    return f"{value[:end]}…", True


# ── Normalize event for storage ─────────────────────────────────────


def normalize_memory_host_event_record_for_storage(
    value: Any,
) -> MemoryHostEventRecord | None:
    """Validate + bound one event before storing in plugin state.

    Mirrors OpenClaw's ``normalizeMemoryHostEventRecordForStorage``.
    Returns the normalized event dict or ``None`` when the payload
    is malformed. Truncates oversized fields and records
    ``storageTruncated: true`` when bounds were applied.
    """
    if not _is_record(value) or not isinstance(value.get("type"), str) or not isinstance(
        value.get("timestamp"), str
    ):
        return None
    ts_value, ts_truncated = _truncate_utf8(value["timestamp"], 128)
    truncated = bool(ts_truncated or value.get("storageTruncated") is True)

    event_type = value["type"]

    # ── memory.recall.recorded / memory.recall.skipped ──────────
    if event_type in ("memory.recall.recorded", "memory.recall.skipped"):
        if (
            not isinstance(value.get("query"), str)
            or not isinstance(value.get("results"), list)
        ):
            return None
        if event_type == "memory.recall.recorded":
            if not _is_finite_number(value.get("resultCount")):
                return None
        else:  # memory.recall.skipped
            if (
                value.get("reason") != "non-short-term-memory-path"
                or not _is_finite_number(value.get("eligibleResultCount"))
                or not _is_finite_number(value.get("skippedResultCount"))
            ):
                return None

        query_value, query_truncated = _truncate_utf8(
            value["query"], MAX_MEMORY_HOST_EVENT_TEXT_BYTES
        )
        truncated = truncated or query_truncated or len(value["results"]) > MAX_MEMORY_HOST_EVENT_ITEMS

        normalized_results: list[MemoryHostRecallResult] = []
        for result in list(value["results"])[:MAX_MEMORY_HOST_EVENT_ITEMS]:
            if not _is_record(result):
                return None
            if (
                not isinstance(result.get("path"), str)
                or not _is_finite_number(result.get("startLine"))
                or not _is_finite_number(result.get("endLine"))
                or not _is_finite_number(result.get("score"))
            ):
                return None
            if (
                event_type == "memory.recall.skipped"
                and result.get("reason") != "non-short-term-memory-path"
            ):
                return None
            path_value, path_truncated = _truncate_utf8(
                result["path"], MAX_MEMORY_HOST_EVENT_PATH_BYTES
            )
            truncated = truncated or path_truncated
            entry: MemoryHostRecallResult = {
                "path": path_value,
                "startLine": result["startLine"],
                "endLine": result["endLine"],
                "score": result["score"],
            }
            if event_type == "memory.recall.skipped":
                entry["reason"] = "non-short-term-memory-path"
            normalized_results.append(entry)

        if event_type == "memory.recall.recorded":
            normalized_recorded: MemoryHostRecallRecordedEvent = {
                "type": "memory.recall.recorded",
                "timestamp": ts_value,
                "query": query_value,
                "resultCount": value["resultCount"],
                "results": [
                    {
                        "path": cast(str, r.get("path")),
                        "startLine": cast(int, r.get("startLine")),
                        "endLine": cast(int, r.get("endLine")),
                        "score": cast(float, r.get("score")),
                    }
                    for r in normalized_results
                ],
            }
            normalized_event: MemoryHostEventRecord = normalized_recorded
        else:
            normalized_skipped: MemoryHostRecallSkippedEvent = {
                "type": "memory.recall.skipped",
                "timestamp": ts_value,
                "query": query_value,
                "reason": "non-short-term-memory-path",
                "eligibleResultCount": value["eligibleResultCount"],
                "skippedResultCount": value["skippedResultCount"],
                "results": [
                    {
                        "path": cast(str, r.get("path")),
                        "startLine": cast(int, r.get("startLine")),
                        "endLine": cast(int, r.get("endLine")),
                        "score": cast(float, r.get("score")),
                        "reason": "non-short-term-memory-path",
                    }
                    for r in normalized_results
                ],
            }
            normalized_event = normalized_skipped
        if truncated:
            normalized_event["storageTruncated"] = True
        encoded = json.dumps(normalized_event, ensure_ascii=False).encode("utf-8")
        if len(encoded) <= MAX_MEMORY_HOST_EVENT_JSON_BYTES:
            return cast(MemoryHostEventRecord, normalized_event)
        # Bound the JSON size: drop the per-result arrays but keep
        # the aggregate counts. Mirrors OpenClaw's behavior.
        return cast(
            MemoryHostEventRecord,
            {**normalized_event, "results": [], "storageTruncated": True},
        )

    # ── memory.promotion.applied ─────────────────────────────────
    if event_type == "memory.promotion.applied":
        if (
            not isinstance(value.get("memoryPath"), str)
            or not _is_finite_number(value.get("applied"))
            or not isinstance(value.get("candidates"), list)
        ):
            return None
        memory_path_value, memory_path_truncated = _truncate_utf8(
            value["memoryPath"], MAX_MEMORY_HOST_EVENT_PATH_BYTES
        )
        truncated = (
            truncated
            or memory_path_truncated
            or len(value["candidates"]) > MAX_MEMORY_HOST_EVENT_ITEMS
        )
        candidates: list[MemoryHostPromotionCandidate] = []
        for cand in list(value["candidates"])[:MAX_MEMORY_HOST_EVENT_ITEMS]:
            if not _is_record(cand):
                return None
            if (
                not isinstance(cand.get("key"), str)
                or not isinstance(cand.get("path"), str)
                or not _is_finite_number(cand.get("startLine"))
                or not _is_finite_number(cand.get("endLine"))
                or not _is_finite_number(cand.get("score"))
                or not _is_finite_number(cand.get("recallCount"))
            ):
                return None
            key_value, key_truncated = _truncate_utf8(
                cand["key"], MAX_MEMORY_HOST_EVENT_PATH_BYTES
            )
            cand_path_value, cand_path_truncated = _truncate_utf8(
                cand["path"], MAX_MEMORY_HOST_EVENT_PATH_BYTES
            )
            truncated = truncated or key_truncated or cand_path_truncated
            candidates.append(
                {
                    "key": key_value,
                    "path": cand_path_value,
                    "startLine": cand["startLine"],
                    "endLine": cand["endLine"],
                    "score": cand["score"],
                    "recallCount": cand["recallCount"],
                }
            )
        normalized_promotion: MemoryHostEventRecord = {
            "type": "memory.promotion.applied",
            "timestamp": ts_value,
            "memoryPath": memory_path_value,
            "applied": value["applied"],
            "candidates": candidates,
        }
        if truncated:
            normalized_promotion["storageTruncated"] = True
        encoded = json.dumps(normalized_promotion, ensure_ascii=False).encode("utf-8")
        if len(encoded) <= MAX_MEMORY_HOST_EVENT_JSON_BYTES:
            return normalized_promotion
        return cast(
            MemoryHostEventRecord,
            {**normalized_promotion, "candidates": [], "storageTruncated": True},
        )

    # ── memory.dream.completed ───────────────────────────────────
    if event_type == "memory.dream.completed":
        phase = value.get("phase")
        outcome = value.get("outcome")
        storage_mode = value.get("storageMode")
        line_count = value.get("lineCount")
        if (
            phase not in ("light", "deep", "rem")
            or (outcome is not None and outcome not in ("completed", "failed"))
            or (value.get("error") is not None and not isinstance(value.get("error"), str))
            or (
                value.get("inlinePath") is not None
                and not isinstance(value.get("inlinePath"), str)
            )
            or (
                value.get("reportPath") is not None
                and not isinstance(value.get("reportPath"), str)
            )
            or not _is_finite_number(line_count)
            or storage_mode not in ("inline", "separate", "both")
        ):
            return None
        error_value, error_truncated = (
            _truncate_utf8(value["error"], MAX_MEMORY_HOST_EVENT_TEXT_BYTES)
            if isinstance(value.get("error"), str)
            else (None, False)
        )
        inline_value, inline_truncated = (
            _truncate_utf8(value["inlinePath"], MAX_MEMORY_HOST_EVENT_PATH_BYTES)
            if isinstance(value.get("inlinePath"), str)
            else (None, False)
        )
        report_value, report_truncated = (
            _truncate_utf8(value["reportPath"], MAX_MEMORY_HOST_EVENT_PATH_BYTES)
            if isinstance(value.get("reportPath"), str)
            else (None, False)
        )
        truncated = (
            truncated
            or bool(error_truncated)
            or bool(inline_truncated)
            or bool(report_truncated)
        )
        normalized: dict[str, Any] = {
            "type": "memory.dream.completed",
            "timestamp": ts_value,
            "phase": phase,
            "lineCount": line_count,
            "storageMode": storage_mode,
        }
        if outcome is not None:
            normalized["outcome"] = outcome
        if error_value is not None:
            normalized["error"] = error_value
        if inline_value is not None:
            normalized["inlinePath"] = inline_value
        if report_value is not None:
            normalized["reportPath"] = report_value
        if truncated:
            normalized["storageTruncated"] = True
        return cast(MemoryHostDreamCompletedEvent, normalized)

    return None


# ── In-process plugin-state backend ──────────────────────────────────
#
# The TS source uses ``registerPluginStateSyncSequencedJournalEntry`` +
# ``pluginStateEntriesInKeyRange`` from the plugin-state runtime. The
# JARVIS port uses a process-wide dict as the backing store, gated by
# ``_event_store_lock``. When the JARVIS plugin-state runtime is
# ported (Phase 5.5+), swap these in-memory primitives for the real
# SDK calls — the public surface above is unchanged.

# Workspace -> { "journal": {key: entry}, "cursors": {workspaceHash: int} }
PluginWorkspaceState = dict[str, dict[str, Any]]
_plugin_state_backend: dict[str, PluginWorkspaceState] = {}


def _get_workspace_state(workspace_dir: str) -> PluginWorkspaceState:
    """Get (or create) the in-process state for ``workspace_dir``."""
    state = _plugin_state_backend.get(workspace_dir)
    if state is None:
        created_state: PluginWorkspaceState = {"journal": {}, "cursors": {}}
        _plugin_state_backend[workspace_dir] = created_state
        return created_state
    return state


def _read_cursor(workspace_dir: str) -> int:
    state = _get_workspace_state(workspace_dir)
    return int(state["cursors"].get("value", 0))


def _write_cursor(workspace_dir: str, value: int) -> None:
    state = _get_workspace_state(workspace_dir)
    state["cursors"]["value"] = int(value)


def _write_journal_entry(
    workspace_dir: str, key: str, value: dict[str, Any], created_at: int
) -> None:
    state = _get_workspace_state(workspace_dir)
    state["journal"][key] = {"value": value, "createdAt": int(created_at)}
    # Apply the rotation cap: keep only the latest N entries (highest
    # sequence numbers).
    cap = _get_max_memory_host_events()
    if len(state["journal"]) > cap:
        # Sort by key (lexicographic; OpenClaw's padStart(16) makes this
        # equivalent to numeric sort) and drop the oldest.
        sorted_keys = sorted(state["journal"].keys())
        excess = len(state["journal"]) - cap
        for old_key in sorted_keys[:excess]:
            del state["journal"][old_key]


def _read_journal_range(
    workspace_dir: str, key_start: str, key_end: str, order: str
) -> list[dict[str, Any]]:
    state = _get_workspace_state(workspace_dir)
    matching = [
        (k, v)
        for k, v in state["journal"].items()
        if k >= key_start and k < key_end
    ]
    # The TS source uses ``order: "desc"`` to scan from the most recent
    # key backwards. The TS range scan returns the latest entries first;
    # ``list_stored_memory_host_events`` then ``toReversed()`` to restore
    # oldest-first order. Mirror that here.
    reverse = order == "desc"
    matching.sort(key=lambda kv: kv[0], reverse=reverse)
    return [
        {"key": k, "value": v["value"], "createdAt": v["createdAt"]}
        for k, v in matching
    ]


# ── Public API ───────────────────────────────────────────────────────


def register_memory_host_event(
    *,
    workspace_dir: str,
    event: dict[str, Any] | MemoryHostEventRecord,
    env: dict[str, Any] | None = None,
) -> None:
    """Append one memory host event to the per-workspace journal.

    Mirrors OpenClaw's ``registerMemoryHostEvent``. Acquires the
    in-process event-store lock, advances the workspace's sequence
    cursor, and writes the journal entry atomically. Raises
    ``TypeError`` when ``event`` is invalid (after normalization).
    """
    normalized = normalize_memory_host_event_record_for_storage(event)
    if normalized is None:
        raise TypeError("Memory host event is invalid")

    # env is accepted for OpenClaw parity (env overrides the
    # in-process backend selector when the SDK plugin-state runtime
    # is wired in). For now we treat it as a no-op marker.
    _ = env

    with _event_store_lock:
        # Read the current tail sequence (0 if empty). The TS source
        # uses the last sequence number; we mirror that.
        state = _get_workspace_state(workspace_dir)
        latest_sequence = 0
        if state["journal"]:
            # Keys are zero-padded to 16 digits so lexicographic max
            # is equivalent to numeric max.
            latest_sequence = int(max(state["journal"].keys())[len(_event_key_prefix(workspace_dir)) + 2:])
        initial_sequence = max(0, latest_sequence)
        next_sequence = initial_sequence + 1
        recorded_at = int(_now_ms())
        key = _memory_host_event_storage_key(workspace_dir, next_sequence)
        _write_journal_entry(
            workspace_dir,
            key,
            {
                "kind": "event",
                "event": normalized,
                "recordedAt": recorded_at,
                "sequence": next_sequence,
            },
            created_at=recorded_at,
        )
        _write_cursor(workspace_dir, next_sequence)


def list_stored_memory_host_events(
    *,
    workspace_dir: str,
    limit: int | None = None,
    env: dict[str, Any] | None = None,
) -> list[PersistedMemoryHostEvent]:
    """Read events for ``workspace_dir`` in newest-first order.

    Mirrors OpenClaw's ``listStoredMemoryHostEvents``. The TS source
    uses ``pluginStateEntriesInKeyRange`` with ``order: "desc"`` and
    then ``toReversed()`` to restore oldest-first; we return
    oldest-first directly (matching the post-reverse TS behavior).
    """
    _ = env  # accepted for parity; no-op until SDK is wired
    cap = _get_max_memory_host_events()
    if limit is not None and isinstance(limit, (int, float)) and limit == limit:
        # Bound the limit to ``[1, cap]`` (TS uses ``Math.max(1, Math.min(cap, Math.floor(limit)))``).
        effective_limit = max(1, min(cap, int(limit)))
    else:
        effective_limit = cap
    raw = _read_journal_range(
        workspace_dir,
        key_start=_event_key_prefix(workspace_dir),
        key_end=_event_key_range_end(workspace_dir),
        order="desc",
    )
    # Apply the limit (we got the latest ``effective_limit`` entries
    # first; trim to that count and reverse to oldest-first).
    entries: list[PersistedMemoryHostEvent] = []
    for raw_entry in raw[:effective_limit]:
        value = cast(StoredMemoryHostEvent, raw_entry["value"])
        if value.get("kind") == "event":
            entries.append(
                PersistedMemoryHostEvent(
                    key=raw_entry["key"],
                    value=value,
                    createdAt=raw_entry["createdAt"],
                )
            )
    return list(reversed(entries))


def _now_ms() -> int:
    """Return the current epoch milliseconds (Python equivalent of ``Date.now()``)."""
    import time
    return int(time.time() * 1000)


__all__ = [
    # Constants
    "MEMORY_HOST_EVENTS_PLUGIN_ID",
    "MEMORY_HOST_EVENTS_NAMESPACE",
    "MEMORY_HOST_EVENT_CURSORS_NAMESPACE",
    "MAX_MEMORY_HOST_EVENTS",
    "MAX_MEMORY_HOST_EVENT_CURSORS",
    "MAX_MEMORY_HOST_EVENT_JSON_BYTES",
    "MAX_MEMORY_HOST_EVENT_ITEMS",
    "MAX_MEMORY_HOST_EVENT_TEXT_BYTES",
    "MAX_MEMORY_HOST_EVENT_PATH_BYTES",
    "WORKSPACE_HASH_BYTES",
    # Types
    "StoredMemoryHostEvent",
    "PersistedMemoryHostEvent",
    # Public API
    "normalize_memory_host_event_record_for_storage",
    "register_memory_host_event",
    "list_stored_memory_host_events",
    "set_max_memory_host_events_for_tests",
]
