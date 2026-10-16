"""Logbook domain types.

Mirrors OpenClaw's ``extensions/logbook/src/types.ts``.

Public types:
- LogbookFrame — one captured screen frame
- LogbookBatch / LogbookBatchStatus — analyzer batch
- LogbookObservation — raw model observation
- LogbookDistraction — within-card distraction window
- LogbookCard / LogbookCardDraft — analyzed card
- LogbookDayStats / LogbookDayStatsCategoryEntry / LogbookDayStatsAppEntry — per-day rolled-up stats
- LogbookStatus / LogbookLastBatchSummary — runtime service status
"""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

# ── Status union ───────────────────────────────────────────

LogbookBatchStatus = Literal["pending", "running", "done", "error"]
VALID_LOGBOOK_BATCH_STATUSES: frozenset[str] = frozenset({"pending", "running", "done", "error"})


# ── Frame + batch + observation + card shapes ─────────────


class LogbookFrame(TypedDict, total=False):
    id: int
    capturedAtMs: int
    day: str
    path: str
    screenIndex: int
    width: Optional[int]
    height: Optional[int]
    byteSize: int
    idle: bool


class LogbookBatch(TypedDict, total=False):
    id: int
    day: str
    startMs: int
    endMs: int
    status: LogbookBatchStatus
    error: Optional[str]
    frameCount: int
    model: Optional[str]


class LogbookObservation(TypedDict, total=False):
    id: int
    batchId: int
    day: str
    startMs: int
    endMs: int
    text: str


class LogbookDistraction(TypedDict, total=False):
    startMs: int
    endMs: int
    title: str


class LogbookCard(TypedDict, total=False):
    id: int
    day: str
    startMs: int
    endMs: int
    title: str
    summary: str
    detail: str
    category: str
    appPrimary: Optional[str]
    appSecondary: Optional[str]
    distractions: list[LogbookDistraction]
    keyframeId: Optional[int]


class LogbookCardDraft(TypedDict, total=False):
    day: str
    startMs: int
    endMs: int
    title: str
    summary: str
    detail: str
    category: str
    appPrimary: Optional[str]
    appSecondary: Optional[str]
    distractions: list[LogbookDistraction]
    keyframeId: Optional[int]


class LogbookDayStatsCategoryEntry(TypedDict, total=False):
    category: str
    ms: int


class LogbookDayStatsAppEntry(TypedDict, total=False):
    domain: str
    ms: int


class LogbookDayStats(TypedDict, total=False):
    trackedMs: int
    distractionMs: int
    categories: list[LogbookDayStatsCategoryEntry]
    apps: list[LogbookDayStatsAppEntry]


class LogbookLastBatchSummary(TypedDict, total=False):
    id: int
    day: str
    status: LogbookBatchStatus
    endMs: int
    error: Optional[str]


class LogbookStatus(TypedDict, total=False):
    captureEnabled: bool
    capturePaused: bool
    captureIntervalSeconds: int
    analysisIntervalMinutes: int
    retentionDays: int
    nodeId: Optional[str]
    nodeName: Optional[str]
    lastCaptureAtMs: Optional[int]
    lastCaptureError: Optional[str]
    pendingFrames: int
    analysisRunning: bool
    lastBatch: Optional[LogbookLastBatchSummary]
    visionModel: Optional[str]
    visionModelSource: Literal["config", "media-defaults", "missing"]
    today: str
    todayCards: int
    timeZone: str


__all__ = [
    "LogbookBatch",
    "LogbookBatchStatus",
    "LogbookCard",
    "LogbookCardDraft",
    "LogbookDayStats",
    "LogbookDayStatsAppEntry",
    "LogbookDayStatsCategoryEntry",
    "LogbookDistraction",
    "LogbookFrame",
    "LogbookLastBatchSummary",
    "LogbookObservation",
    "LogbookStatus",
    "VALID_LOGBOOK_BATCH_STATUSES",
]
