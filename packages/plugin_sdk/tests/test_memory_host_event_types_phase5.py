"""Tests for jarvis_sdk.memory_host_event_types (Phase 5.1a).

Mirrors the TypeScript test patterns from
``src/memory-host-sdk/event-types.test.ts``.
"""

from __future__ import annotations


from typing import cast

from jarvis_sdk.memory_host_event_types import (
    MemoryHostDreamCompletedEvent,
    MemoryHostPromotionAppliedEvent,
    MemoryHostRecallRecordedEvent,
    MemoryHostRecallSkippedEvent,
    MemoryHostPromotionCandidate,
    MemoryHostRecallResult,
)


# ── Type-shape presence (TypedDict instances are dicts) ──────────────


def test_recall_recorded_event_shape() -> None:
    """Required fields are all present + correctly typed."""
    event: MemoryHostRecallRecordedEvent = {
        "type": "memory.recall.recorded",
        "timestamp": "2025-12-15T12:00:00Z",
        "query": "test query",
        "resultCount": 2,
        "results": [
            {
                "path": "memory/foo.md",
                "startLine": 1,
                "endLine": 5,
                "score": 0.95,
            },
            {
                "path": "memory/bar.md",
                "startLine": 10,
                "endLine": 15,
                "score": 0.80,
            },
        ],
    }
    assert event["type"] == "memory.recall.recorded"
    assert event["resultCount"] == 2
    assert len(event["results"]) == 2
    assert event["results"][0]["path"] == "memory/foo.md"


def test_recall_skipped_event_shape() -> None:
    """Skipped event has reason + eligible + skipped counts."""
    event: MemoryHostRecallSkippedEvent = {
        "type": "memory.recall.skipped",
        "timestamp": "2025-12-15T12:00:00Z",
        "query": "test query",
        "reason": "non-short-term-memory-path",
        "eligibleResultCount": 5,
        "skippedResultCount": 2,
        "results": [
            {
                "path": "memory/not-short-term.md",
                "startLine": 1,
                "endLine": 5,
                "score": 0.90,
                "reason": "non-short-term-memory-path",
            }
        ],
    }
    assert event["type"] == "memory.recall.skipped"
    assert event["reason"] == "non-short-term-memory-path"
    assert event["eligibleResultCount"] == 5
    assert event["skippedResultCount"] == 2


def test_promotion_applied_event_shape() -> None:
    """Promotion event includes memoryPath + applied + candidates."""
    event: MemoryHostPromotionAppliedEvent = {
        "type": "memory.promotion.applied",
        "timestamp": "2025-12-15T12:00:00Z",
        "memoryPath": "MEMORY.md",
        "applied": 3,
        "candidates": [
            {
                "key": "k1",
                "path": "memory/2025-12-14.md",
                "startLine": 1,
                "endLine": 5,
                "score": 0.95,
                "recallCount": 5,
            }
        ],
    }
    assert event["type"] == "memory.promotion.applied"
    assert event["memoryPath"] == "MEMORY.md"
    assert event["applied"] == 3
    assert event["candidates"][0]["recallCount"] == 5


def test_dream_completed_event_shape() -> None:
    """Dream completed event has phase + lineCount + storageMode."""
    event = cast(
        MemoryHostDreamCompletedEvent,
        {
            "type": "memory.dream.completed",
            "timestamp": "2025-12-15T12:00:00Z",
            "phase": "light",
            "outcome": "completed",
            "lineCount": 10,
            "storageMode": "inline",
        },
    )
    assert event["type"] == "memory.dream.completed"
    assert event["phase"] == "light"
    assert event["outcome"] == "completed"
    assert event["lineCount"] == 10
    assert event["storageMode"] == "inline"


def test_event_record_union_contains_all_variants() -> None:
    """``MemoryHostEventRecord`` is the documented union (Python typing)."""
    # We can't fully assert union semantics at runtime in Python, but
    # we can construct all four variants and confirm the discriminated
    # ``type`` field is correct.
    variants = [
        {
            "type": "memory.recall.recorded",
            "timestamp": "t",
            "query": "q",
            "resultCount": 0,
            "results": [],
        },
        {
            "type": "memory.recall.skipped",
            "timestamp": "t",
            "query": "q",
            "reason": "non-short-term-memory-path",
            "eligibleResultCount": 0,
            "skippedResultCount": 0,
            "results": [],
        },
        {
            "type": "memory.promotion.applied",
            "timestamp": "t",
            "memoryPath": "MEMORY.md",
            "applied": 0,
            "candidates": [],
        },
        {
            "type": "memory.dream.completed",
            "timestamp": "t",
            "phase": "light",
            "lineCount": 0,
            "storageMode": "inline",
        },
    ]
    types = {v["type"] for v in variants}
    assert types == {
        "memory.recall.recorded",
        "memory.recall.skipped",
        "memory.promotion.applied",
        "memory.dream.completed",
    }


# ── storageTruncated mixin field ──────────────────────────────────────


def test_recall_recorded_with_storage_truncated() -> None:
    """``storageTruncated: true`` is preserved on the event."""
    event: MemoryHostRecallRecordedEvent = {
        "type": "memory.recall.recorded",
        "timestamp": "2025-12-15T12:00:00Z",
        "query": "q",
        "resultCount": 1,
        "results": [],
        "storageTruncated": True,
    }
    assert event.get("storageTruncated") is True


def test_dream_completed_with_optional_fields() -> None:
    """outcome, error, inlinePath, reportPath are all optional."""
    event = cast(
        MemoryHostDreamCompletedEvent,
        {
            "type": "memory.dream.completed",
            "timestamp": "2025-12-15T12:00:00Z",
            "phase": "rem",
            "lineCount": 5,
            "storageMode": "both",
        },
    )
    # Optional fields absent
    assert "outcome" not in event
    assert "error" not in event
    assert "inlinePath" not in event
    assert "reportPath" not in event


def test_promotion_candidate_field_names() -> None:
    """Candidate fields use OpenClaw's exact key names."""
    cand: MemoryHostPromotionCandidate = {
        "key": "x",
        "path": "p",
        "startLine": 1,
        "endLine": 2,
        "score": 0.5,
        "recallCount": 3,
    }
    assert set(cand.keys()) == {"key", "path", "startLine", "endLine", "score", "recallCount"}


def test_recall_result_field_names() -> None:
    """Recall result fields match OpenClaw's key shape (no recallCount)."""
    result: MemoryHostRecallResult = {
        "path": "p",
        "startLine": 1,
        "endLine": 2,
        "score": 0.5,
    }
    assert set(result.keys()) == {"path", "startLine", "endLine", "score"}


def test_recall_result_includes_reason_when_skipped() -> None:
    """``reason`` is added for skipped events only."""
    skipped: MemoryHostRecallResult = {
        "path": "p",
        "startLine": 1,
        "endLine": 2,
        "score": 0.5,
        "reason": "non-short-term-memory-path",
    }
    assert skipped["reason"] == "non-short-term-memory-path"


# ── Phase + storageMode enum coverage ──────────────────────────────


def test_dream_phase_values() -> None:
    """The phase field accepts the documented OpenClaw values."""
    for phase in ("light", "rem", "deep"):
        event: MemoryHostDreamCompletedEvent = {
            "type": "memory.dream.completed",
            "timestamp": "t",
            "phase": phase,  # type: ignore[typeddict-item]
            "lineCount": 0,
            "storageMode": "inline",
        }
        assert event["phase"] == phase


def test_dream_storage_mode_values() -> None:
    """The storageMode field accepts the documented values."""
    for mode in ("inline", "separate", "both"):
        event: MemoryHostDreamCompletedEvent = {
            "type": "memory.dream.completed",
            "timestamp": "t",
            "phase": "light",
            "lineCount": 0,
            "storageMode": mode,  # type: ignore[typeddict-item]
        }
        assert event["storageMode"] == mode


def test_dream_outcome_values() -> None:
    """The outcome field accepts the documented values."""
    for outcome in ("completed", "failed"):
        event: MemoryHostDreamCompletedEvent = {
            "type": "memory.dream.completed",
            "timestamp": "t",
            "phase": "light",
            "lineCount": 0,
            "storageMode": "inline",
            "outcome": outcome,  # type: ignore[typeddict-item]
        }
        assert event["outcome"] == outcome
