"""jarvis.shared.session_usage_timeseries_types — usage time-series types.

OpenClaw parity: mirrors
``openclaw-main/src/shared/session-usage-timeseries-types.ts``.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict


class SessionUsageTimePoint(TypedDict, total=False):
    """Usage totals for one sampled point in a session usage time series.

    Mirrors :type:`SessionUsageTimePoint`
    (``shared/session-usage-timeseries-types.ts``).
    """
    timestamp: int  # Unix epoch milliseconds
    input: int
    output: int
    cacheRead: int
    cacheWrite: int
    totalTokens: int
    cost: float
    cumulativeTokens: int
    cumulativeCost: float


class SessionUsageTimeSeries(TypedDict, total=False):
    """Downsampled usage series for a single session.

    Mirrors :type:`SessionUsageTimeSeries`
    (``shared/session-usage-timeseries-types.ts``).
    """
    sessionId: str
    points: List[SessionUsageTimePoint]


__all__ = ["SessionUsageTimePoint", "SessionUsageTimeSeries"]
