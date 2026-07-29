"""Logbook domain types.

Mirrors OpenClaw's ``extensions/logbook/src/types.ts``.

Public types (mirrors the TS source):
- LogbookFrame — one captured screen frame
- LogbookBatch / LogbookBatchStatus — analyzer batch
- LogbookObservation — raw model observation
- LogbookDistraction — within-card distraction window
- LogbookCard / LogbookCardDraft — analyzed card
- LogbookDayStats — per-day rolled-up stats

Python adaptations (documented in code):
- TS optional fields → Python ``total=False`` TypedDict
- TS union of string literals → Python ``Literal[...]``
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict


# ── Status union ───────────────────────────────────────────


LogbookBatchStatus = Literal["pending", "running", "done", "error"]
VALID_LOGBOOK_BATCH_STATUSES: frozenset[str] = frozenset(
    {"pending", "running", "done", "error"}
)


# ── Frame + batch + observation + card shapes ─────────────


class LogbookFrame(TypedDict, total=False):
    id: int
    capturedAtMs: int
    day: str
    path: str
    screenIndex: int
    width: int
    height: int
    byteSize: int
    idle: bool


class LogbookBatch(TypedDict, total=False):
    id: int
    day: str
    startMs: int
    endMs: int
    status: LogbookBatchStatus
    error: str
    frameCount: int
    model: str


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
    appPrimary: str
    appSecondary: str
    distractions: list[LogbookDistraction]
    keyframeId: int


LogbookCardDraft = LogbookCard  # ``Omit<LogbookCard, "id">`` — Python equivalent: same shape


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
    "LogbookObservation",
    "VALID_LOGBOOK_BATCH_STATUSES",
]
