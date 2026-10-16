"""jarvis.shared.usage_types — usage accounting response types.

OpenClaw parity: mirrors ``openclaw-main/src/shared/usage-types.ts``.
"""
from __future__ import annotations

from typing import List, TypedDict, Union


class SessionUsageOrigin(TypedDict, total=False):
    label: str
    provider: str
    surface: str
    chatType: str
    from_: str
    to: str
    accountId: str
    threadId: Union[str, int]


class SessionUsageEntry(TypedDict, total=False):
    """One session or session-family row.

    Mirrors :type:`SessionUsageEntry` (``shared/usage-types.ts``).
    """
    key: str
    label: str
    sessionId: str
    scope: str  # "instance" | "family"
    sessionFamilyKey: str
    currentSessionId: str
    includedSessionIds: List[str]
    historicalInstanceCount: int
    updatedAt: int
    agentId: str
    channel: str
    chatType: str
    origin: SessionUsageOrigin
    modelOverride: str
    providerOverride: str
    modelProvider: str
    model: str
    usage: dict  # SessionCostSummary | null
    contextWeight: dict  # SessionSystemPromptReport | null


class SessionsUsageAggregates(TypedDict, total=False):
    sessionCount: int
    longestSessionDurationMs: int
    messages: dict
    tools: dict
    byModel: List[dict]
    byProvider: List[dict]
    byAgent: List[dict]
    byChannel: List[dict]
    latency: dict
    dailyLatency: List[dict]
    modelDaily: List[dict]
    daily: List[dict]


class SessionsUsageResult(TypedDict, total=False):
    updatedAt: int
    startDate: str
    endDate: str
    sessions: List[SessionUsageEntry]
    totals: dict
    aggregates: SessionsUsageAggregates
    cacheStatus: dict


__all__ = [
    "SessionUsageEntry",
    "SessionsUsageAggregates",
    "SessionsUsageResult",
]
