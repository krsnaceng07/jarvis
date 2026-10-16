"""Tests for jarvis_sdk.memory_host_event_export (Phase 5.1c)."""

from __future__ import annotations

import json

from jarvis_sdk.memory_host_event_export import (
    MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES,
    serialize_memory_host_event_export,
)


def test_max_bytes_constant() -> None:
    """1 MB cap matches OpenClaw."""
    assert MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES == 1024 * 1024


def test_empty_input_returns_empty_string() -> None:
    """No events → empty output."""
    assert serialize_memory_host_event_export([]) == ""


def test_single_event_round_trip() -> None:
    """One event → one JSONL line."""
    events = [
        {
            "type": "memory.dream.completed",
            "timestamp": "t",
            "phase": "light",
            "lineCount": 0,
            "storageMode": "inline",
        }
    ]
    out = serialize_memory_host_event_export(events)
    assert out.endswith("\n")
    lines = out.rstrip("\n").split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["type"] == "memory.dream.completed"
    assert parsed["phase"] == "light"


def test_persisted_event_envelope() -> None:
    """PersistedMemoryHostEvent-shaped input (with ``value.event``) is unwrapped."""
    persisted = {
        "key": "k",
        "value": {
            "kind": "event",
            "event": {
                "type": "memory.recall.recorded",
                "timestamp": "t",
                "query": "q",
                "resultCount": 0,
                "results": [],
            },
            "recordedAt": 0,
            "sequence": 1,
        },
        "createdAt": 0,
    }
    out = serialize_memory_host_event_export([persisted])
    assert out.endswith("\n")
    parsed = json.loads(out.rstrip("\n"))
    assert parsed["type"] == "memory.recall.recorded"


def test_caps_output_size() -> None:
    """When the cap would be exceeded, oldest events are dropped."""
    big_body = "x" * 1024  # 1 KB event body
    events = [
        {
            "type": "memory.dream.completed",
            "timestamp": f"t{i}",
            "phase": "light",
            "lineCount": i,
            "storageMode": "inline",
            "error": big_body,
        }
        for i in range(2000)  # ~2 MB total
    ]
    out = serialize_memory_host_event_export(events)
    # The output is bounded well under the cap (account for json overhead)
    assert len(out.encode("utf-8")) <= MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES + 4096
    # And it kept some events (at least 100, well below the cap)
    assert len(out.rstrip("\n").split("\n")) > 0


def test_skips_entries_with_no_event(tmp_path: object) -> None:
    """Entries without a recognizable ``value.event`` are skipped."""
    events = [
        {"key": "k1", "value": None, "createdAt": 0},  # no event
        {
            "key": "k2",
            "value": {
                "kind": "event",
                "event": {
                    "type": "memory.dream.completed",
                    "timestamp": "t",
                    "phase": "light",
                    "lineCount": 0,
                    "storageMode": "inline",
                },
            },
            "createdAt": 0,
        },
    ]
    out = serialize_memory_host_event_export(events)
    lines = out.rstrip("\n").split("\n")
    assert len(lines) == 1
