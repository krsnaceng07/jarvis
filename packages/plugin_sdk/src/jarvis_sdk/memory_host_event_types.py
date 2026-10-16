"""jarvis_sdk.memory_host_event_types — public event types for memory host.

OpenClaw parity: mirrors ``src/memory-host-sdk/event-types.ts`` (80 LOC).
Defines the durable event schemas that the memory host + plugins
emit and consume. Type-only module; no runtime code.

Key port decisions:
- TS discriminated union types map to ``TypedDict`` + ``Literal``.
- camelCase fields preserved verbatim (OpenClaw JSON shape).
- ``MemoryHostEventStorageMetadata`` is a mixin (intersection in TS);
  in Python we model it as a TypedDict with ``total=False`` for
  the optional ``storageTruncated`` field and require callers to
  spread it into concrete event types.
"""

from __future__ import annotations

from typing import Literal, TypedDict

# Phase name from the dreaming pipeline (already ported in
# extensions/memory_core/dreaming_shared.py). Reuse via duck typing
# here to avoid an import cycle.
MemoryDreamingPhaseName = Literal["light", "rem", "deep", "shadow-trial"]
MemoryDreamOutcome = Literal["completed", "failed"]
MemoryStorageMode = Literal["inline", "separate", "both"]


class MemoryHostEventStorageMetadata(TypedDict, total=False):
    """Mixin for events that may have been bounded before persistence.

    ``storageTruncated: true`` means diagnostic detail was bounded
    before persistence; aggregate counts stay exact. Mirrors the
    OpenClaw ``MemoryHostEventStorageMetadata`` type.
    """

    storageTruncated: Literal[True]


class MemoryHostRecallResult(TypedDict, total=False):
    """A single recall result line within a recall event.

    Mirrors the per-result record used in
    ``MemoryHostRecallRecordedEvent.results`` and
    ``MemoryHostRecallSkippedEvent.results``.
    """

    path: str
    startLine: int
    endLine: int
    score: float
    # Only set on skipped events; the JSON literal matches OpenClaw.
    reason: Literal["non-short-term-memory-path"]


class MemoryHostRecallRecordedEvent(MemoryHostEventStorageMetadata):
    """Event emitted when a recall query records selected memory snippets.

    Mirrors OpenClaw's ``MemoryHostRecallRecordedEvent``.
    """

    type: Literal["memory.recall.recorded"]
    timestamp: str
    query: str
    resultCount: int
    results: list[MemoryHostRecallResult]


class MemoryHostRecallSkippedEvent(MemoryHostEventStorageMetadata):
    """Event emitted when recall hits are excluded from short-term promotion.

    Mirrors OpenClaw's ``MemoryHostRecallSkippedEvent``.
    """

    type: Literal["memory.recall.skipped"]
    timestamp: str
    query: str
    reason: Literal["non-short-term-memory-path"]
    eligibleResultCount: int
    skippedResultCount: int
    results: list[MemoryHostRecallResult]


class MemoryHostPromotionCandidate(TypedDict, total=False):
    """A single promotion candidate within a promotion-applied event."""

    key: str
    path: str
    startLine: int
    endLine: int
    score: float
    recallCount: int


class MemoryHostPromotionAppliedEvent(MemoryHostEventStorageMetadata):
    """Event emitted when deep-dream candidates are promoted into durable memory.

    Mirrors OpenClaw's ``MemoryHostPromotionAppliedEvent``.
    """

    type: Literal["memory.promotion.applied"]
    timestamp: str
    memoryPath: str
    applied: int
    candidates: list[MemoryHostPromotionCandidate]


class MemoryHostDreamCompletedEvent(MemoryHostEventStorageMetadata):
    """Event emitted after a dreaming phase writes inline memory and/or reports.

    Mirrors OpenClaw's ``MemoryHostDreamCompletedEvent``. ``outcome``
    is optional for older event-log compatibility (readers should treat
    absent as "completed").
    """

    type: Literal["memory.dream.completed"]
    timestamp: str
    phase: MemoryDreamingPhaseName
    outcome: MemoryDreamOutcome
    error: str
    inlinePath: str
    reportPath: str
    lineCount: int
    storageMode: MemoryStorageMode


# Discriminated union (loosely-typed for the runtime: Python TypedDicts
# don't enforce unions, so this is documentation + a typing alias).
MemoryHostEvent = (
    MemoryHostRecallRecordedEvent | MemoryHostPromotionAppliedEvent | MemoryHostDreamCompletedEvent
)

# Full event record schema: includes opt-in diagnostic variants.
MemoryHostEventRecord = MemoryHostEvent | MemoryHostRecallSkippedEvent


__all__ = [
    "MemoryDreamingPhaseName",
    "MemoryDreamOutcome",
    "MemoryStorageMode",
    "MemoryHostEventStorageMetadata",
    "MemoryHostRecallResult",
    "MemoryHostRecallRecordedEvent",
    "MemoryHostRecallSkippedEvent",
    "MemoryHostPromotionCandidate",
    "MemoryHostPromotionAppliedEvent",
    "MemoryHostDreamCompletedEvent",
    "MemoryHostEvent",
    "MemoryHostEventRecord",
]
