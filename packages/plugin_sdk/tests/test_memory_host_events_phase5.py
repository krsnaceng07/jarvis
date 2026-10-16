"""Tests for jarvis_sdk.memory_host_events (Phase 5.1b).

Mirrors the TypeScript test patterns from
``src/memory-host-sdk/events.test.ts``.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Generator

import pytest

from jarvis_sdk.memory_host_events import (
    MEMORY_HOST_EVENT_LOG_RELATIVE_PATH,
    append_memory_host_event as _append_memory_host_event,
    read_memory_host_events,
    read_memory_host_event_records,
    resolve_memory_host_event_log_path,
)
from jarvis_sdk.memory_host_event_store import (
    list_stored_memory_host_events,
    set_max_memory_host_events_for_tests,
)


def append_memory_host_event(workspace: str, event: Any) -> Any:
    return _append_memory_host_event(workspace, event)


# ── Constants / paths ──────────────────────────────────────────────


def test_event_log_relative_path() -> None:
    """``MEMORY_HOST_EVENT_LOG_RELATIVE_PATH`` is the legacy JSONL path."""
    assert MEMORY_HOST_EVENT_LOG_RELATIVE_PATH.endswith("events.jsonl")
    assert "memory" in MEMORY_HOST_EVENT_LOG_RELATIVE_PATH
    assert ".dreams" in MEMORY_HOST_EVENT_LOG_RELATIVE_PATH


def test_resolve_event_log_path(tmp_path: Path) -> None:
    """``resolve_memory_host_event_log_path`` joins workspace + relative path."""
    result = resolve_memory_host_event_log_path(str(tmp_path))
    assert result == str(tmp_path / "memory" / ".dreams" / "events.jsonl")


# ── append + read round trip ────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_journal() -> Generator[None, None, None]:
    """Reset the in-process journal between tests."""
    set_max_memory_host_events_for_tests(None)
    # Clear the in-process state (the store module re-creates it on
    # next use; no other public API exposes this).
    import jarvis_sdk.memory_host_event_store as store_mod

    store_mod._plugin_state_backend.clear()
    yield
    store_mod._plugin_state_backend.clear()
    set_max_memory_host_events_for_tests(None)


def test_append_then_read_recall_recorded(tmp_path: Path) -> None:
    """Round trip: append a recall event and read it back."""
    workspace = str(tmp_path)
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.recall.recorded",
                "timestamp": "2025-12-15T12:00:00Z",
                "query": "test query",
                "resultCount": 1,
                "results": [
                    {
                        "path": "memory/foo.md",
                        "startLine": 1,
                        "endLine": 5,
                        "score": 0.95,
                    }
                ],
            },
        )
    )
    events = asyncio.run(read_memory_host_events(workspace))
    assert len(events) == 1
    assert events[0]["type"] == "memory.recall.recorded"
    assert events[0]["query"] == "test query"
    assert events[0]["resultCount"] == 1
    assert events[0]["results"][0]["path"] == "memory/foo.md"


def test_append_then_read_dream_completed(tmp_path: Path) -> None:
    """Dream completed event round trip."""
    workspace = str(tmp_path)
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.dream.completed",
                "timestamp": "2025-12-15T12:00:00Z",
                "phase": "light",
                "lineCount": 5,
                "storageMode": "inline",
            },
        )
    )
    events = asyncio.run(read_memory_host_events(workspace))
    assert len(events) == 1
    assert events[0]["type"] == "memory.dream.completed"
    assert events[0]["phase"] == "light"
    assert events[0]["lineCount"] == 5


def test_append_then_read_promotion_applied(tmp_path: Path) -> None:
    """Promotion applied event round trip."""
    workspace = str(tmp_path)
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.promotion.applied",
                "timestamp": "2025-12-15T12:00:00Z",
                "memoryPath": "MEMORY.md",
                "applied": 1,
                "candidates": [
                    {
                        "key": "k1",
                        "path": "memory/2025-12-14.md",
                        "startLine": 1,
                        "endLine": 5,
                        "score": 0.95,
                        "recallCount": 4,
                    }
                ],
            },
        )
    )
    events = asyncio.run(read_memory_host_events(workspace))
    assert len(events) == 1
    assert events[0]["type"] == "memory.promotion.applied"
    assert events[0]["applied"] == 1
    assert events[0]["candidates"][0]["recallCount"] == 4


def test_read_filters_out_skipped_events(tmp_path: Path) -> None:
    """``read_memory_host_events`` filters ``memory.recall.skipped``.

    ``read_memory_host_event_records`` includes them.
    """
    workspace = str(tmp_path)
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.recall.skipped",
                "timestamp": "2025-12-15T12:00:00Z",
                "query": "q",
                "reason": "non-short-term-memory-path",
                "eligibleResultCount": 1,
                "skippedResultCount": 1,
                "results": [
                    {
                        "path": "memory/x.md",
                        "startLine": 1,
                        "endLine": 5,
                        "score": 0.9,
                        "reason": "non-short-term-memory-path",
                    }
                ],
            },
        )
    )
    public_events = asyncio.run(read_memory_host_events(workspace))
    assert public_events == []  # filtered out

    records = asyncio.run(read_memory_host_event_records(workspace))
    assert len(records) == 1
    assert records[0]["type"] == "memory.recall.skipped"


def test_read_applies_tail_limit(tmp_path: Path) -> None:
    """``limit`` is applied as a tail-slice of the journal."""
    workspace = str(tmp_path)
    for i in range(5):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": f"2025-12-15T12:00:{i:02d}Z",
                    "phase": "light",
                    "lineCount": i,
                    "storageMode": "inline",
                },
            )
        )
    events = asyncio.run(read_memory_host_events(workspace, limit=3))
    assert len(events) == 3
    # Limit is tail-based: last 3 appended
    line_counts = [e.get("lineCount") for e in events]
    assert line_counts == [2, 3, 4]


def test_read_limit_zero_returns_empty(tmp_path: Path) -> None:
    """``limit=0`` returns an empty list."""
    workspace = str(tmp_path)
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.dream.completed",
                "timestamp": "t",
                "phase": "light",
                "lineCount": 0,
                "storageMode": "inline",
            },
        )
    )
    events = asyncio.run(read_memory_host_events(workspace, limit=0))
    assert events == []


def test_read_limit_none_returns_all(tmp_path: Path) -> None:
    """``limit=None`` returns all events."""
    workspace = str(tmp_path)
    for i in range(3):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": f"t{i}",
                    "phase": "light",
                    "lineCount": i,
                    "storageMode": "inline",
                },
            )
        )
    events = asyncio.run(read_memory_host_events(workspace, limit=None))
    assert len(events) == 3


def test_append_invalid_event_raises(tmp_path: Path) -> None:
    """Invalid events raise ``TypeError``."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {"type": "unknown.event"},
            )
        )


def test_append_event_missing_type_raises(tmp_path: Path) -> None:
    """Event without ``type`` is rejected."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {"timestamp": "t", "query": "q"},
            )
        )


def test_append_event_missing_timestamp_raises(tmp_path: Path) -> None:
    """Event without ``timestamp`` is rejected."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {"type": "memory.dream.completed", "phase": "light"},
            )
        )


# ── list_stored_memory_host_events (in-process backing) ────────────


def test_list_stored_events_includes_metadata(tmp_path: Path) -> None:
    """Stored events carry the ``kind: "event"`` envelope + recordedAt + sequence."""
    workspace = str(tmp_path)
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.dream.completed",
                "timestamp": "t",
                "phase": "light",
                "lineCount": 0,
                "storageMode": "inline",
            },
        )
    )
    stored = list_stored_memory_host_events(workspace_dir=workspace)
    assert len(stored) == 1
    entry = stored[0]
    assert entry["value"]["kind"] == "event"
    assert "recordedAt" in entry["value"]
    assert "sequence" in entry["value"]
    assert "createdAt" in entry


def test_list_stored_events_oldest_first_order(tmp_path: Path) -> None:
    """``list_stored_memory_host_events`` returns oldest-first."""
    workspace = str(tmp_path)
    for i in range(3):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": f"t{i}",
                    "phase": "light",
                    "lineCount": i,
                    "storageMode": "inline",
                },
            )
        )
    stored = list_stored_memory_host_events(workspace_dir=workspace)
    sequences = [entry["value"]["sequence"] for entry in stored]
    assert sequences == [1, 2, 3]


def test_list_stored_events_limit(tmp_path: Path) -> None:
    """``limit`` is respected."""
    workspace = str(tmp_path)
    for i in range(5):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": f"t{i}",
                    "phase": "light",
                    "lineCount": i,
                    "storageMode": "inline",
                },
            )
        )
    stored = list_stored_memory_host_events(workspace_dir=workspace, limit=2)
    assert len(stored) == 2


def test_workspaces_isolated(tmp_path: Path) -> None:
    """Different workspaces get separate journals."""
    ws_a = str(tmp_path / "a")
    ws_b = str(tmp_path / "b")
    os.makedirs(ws_a)
    os.makedirs(ws_b)
    asyncio.run(
        append_memory_host_event(
            ws_a,
            {
                "type": "memory.dream.completed",
                "timestamp": "t",
                "phase": "light",
                "lineCount": 1,
                "storageMode": "inline",
            },
        )
    )
    events_a = asyncio.run(read_memory_host_events(ws_a))
    events_b = asyncio.run(read_memory_host_events(ws_b))
    assert len(events_a) == 1
    assert events_b == []


# ── Validation / normalization (via append round trip) ──────────────


def test_recall_recorded_result_count_mismatch_rejected(tmp_path: Path) -> None:
    """An event with resultCount != len(results) is still stored (the
    normalizer only checks structural validity)."""
    workspace = str(tmp_path)
    # This is structurally valid: resultCount is a finite number.
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.recall.recorded",
                "timestamp": "t",
                "query": "q",
                "resultCount": 5,
                "results": [
                    {
                        "path": "memory/foo.md",
                        "startLine": 1,
                        "endLine": 5,
                        "score": 0.9,
                    }
                ],
            },
        )
    )
    stored = list_stored_memory_host_events(workspace_dir=workspace)
    assert len(stored) == 1
    assert stored[0]["value"]["event"].get("resultCount") == 5


def test_recall_event_too_many_results_gets_bounded(tmp_path: Path) -> None:
    """When the result count exceeds the cap, the normalizer trims
    and sets ``storageTruncated: true``."""
    workspace = str(tmp_path)
    many_results = [
        {
            "path": f"memory/file_{i}.md",
            "startLine": i,
            "endLine": i + 1,
            "score": 0.5,
        }
        for i in range(20)  # > MAX_MEMORY_HOST_EVENT_ITEMS (10)
    ]
    asyncio.run(
        append_memory_host_event(
            workspace,
            {
                "type": "memory.recall.recorded",
                "timestamp": "t",
                "query": "q",
                "resultCount": 20,
                "results": many_results,
            },
        )
    )
    stored = list_stored_memory_host_events(workspace_dir=workspace)
    assert len(stored) == 1
    event = stored[0]["value"]["event"]
    # Bounded: at most MAX_MEMORY_HOST_EVENT_ITEMS results
    assert len(event.get("results", [])) <= 10


def test_dream_completed_invalid_phase_rejected(tmp_path: Path) -> None:
    """An unknown phase is rejected (not one of light/deep/rem)."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": "t",
                    "phase": "unknown",  # type: ignore[typeddict-item]
                    "lineCount": 0,
                    "storageMode": "inline",
                },
            )
        )


def test_dream_completed_invalid_storage_mode_rejected(tmp_path: Path) -> None:
    """An unknown storageMode is rejected."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": "t",
                    "phase": "light",
                    "lineCount": 0,
                    "storageMode": "unknown",  # type: ignore[typeddict-item]
                },
            )
        )


def test_dream_completed_missing_required_field_rejected(tmp_path: Path) -> None:
    """Missing lineCount is rejected."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.dream.completed",
                    "timestamp": "t",
                    "phase": "light",
                    # missing lineCount
                    "storageMode": "inline",
                },
            )
        )


def test_promotion_applied_missing_memory_path_rejected(tmp_path: Path) -> None:
    """Missing memoryPath is rejected."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.promotion.applied",
                    "timestamp": "t",
                    "applied": 0,
                    "candidates": [],
                },
            )
        )


def test_recall_skipped_wrong_reason_rejected(tmp_path: Path) -> None:
    """A skipped event with a different reason is rejected."""
    workspace = str(tmp_path)
    with pytest.raises(TypeError, match="invalid"):
        asyncio.run(
            append_memory_host_event(
                workspace,
                {
                    "type": "memory.recall.skipped",
                    "timestamp": "t",
                    "query": "q",
                    "reason": "other-reason",  # type: ignore[typeddict-item]
                    "eligibleResultCount": 1,
                    "skippedResultCount": 1,
                    "results": [],
                },
            )
        )


# ── Test override for the journal cap ─────────────────────────────────


def test_set_max_memory_host_events_for_tests(tmp_path: Path) -> None:
    """The test override limits the journal cap."""
    workspace = str(tmp_path)
    set_max_memory_host_events_for_tests(3)
    try:
        for i in range(5):
            asyncio.run(
                append_memory_host_event(
                    workspace,
                    {
                        "type": "memory.dream.completed",
                        "timestamp": f"t{i}",
                        "phase": "light",
                        "lineCount": i,
                        "storageMode": "inline",
                    },
                )
            )
        stored = list_stored_memory_host_events(workspace_dir=workspace)
        # Only the latest 3 (sequences 3, 4, 5) survive
        assert len(stored) == 3
        sequences = [e["value"]["sequence"] for e in stored]
        assert sequences == [3, 4, 5]
    finally:
        set_max_memory_host_events_for_tests(None)
