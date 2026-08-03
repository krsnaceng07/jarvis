"""jarvis.shared.usage_aggregates — usage aggregate builders.

OpenClaw parity: mirrors ``openclaw-main/src/shared/usage-aggregates.ts``.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Generic, List, Optional, TypeVar


TTotals = TypeVar("TTotals", bound=dict)
TDaily = TypeVar("TDaily", bound=dict)
TModelDaily = TypeVar("TModelDaily", bound=dict)


def merge_usage_latency(totals: dict, latency: Optional[dict]) -> None:
    """Merge latency summaries into a totals accumulator (mutates ``totals``).

    Mirrors :func:`mergeUsageLatency` (``shared/usage-aggregates.ts``).
    """
    if not latency or not isinstance(latency, dict):
        return
    if latency.get("count", 0) <= 0:
        return
    totals["count"] = totals.get("count", 0) + latency["count"]
    totals["sum"] = totals.get("sum", 0) + latency["avgMs"] * latency["count"]
    totals["min"] = min(totals.get("min", math.inf), latency["minMs"])
    totals["max"] = max(totals.get("max", 0), latency["maxMs"])
    totals["p95Max"] = max(totals.get("p95Max", 0), latency["p95Ms"])


def merge_usage_daily_latency(
    daily_latency_map: Dict[str, dict],
    daily_latency: Optional[List[dict]] = None,
) -> None:
    """Group daily latency summaries by date (mutates ``daily_latency_map``).

    Mirrors :func:`mergeUsageDailyLatency`
    (``shared/usage-aggregates.ts``).
    """
    for day in daily_latency or []:
        if not isinstance(day, dict):
            continue
        existing = daily_latency_map.get(day["date"]) or {
            "date": day["date"],
            "count": 0,
            "sum": 0,
            "min": math.inf,
            "max": 0,
            "p95Max": 0,
        }
        existing["count"] += day["count"]
        existing["sum"] += day["avgMs"] * day["count"]
        existing["min"] = min(existing["min"], day["minMs"])
        existing["max"] = max(existing["max"], day["maxMs"])
        existing["p95Max"] = max(existing["p95Max"], day["p95Ms"])
        daily_latency_map[day["date"]] = existing


def build_usage_aggregate_tail(params: dict) -> dict:
    """Build deterministic usage aggregate arrays for API responses.

    Mirrors :func:`buildUsageAggregateTail``
    (``shared/usage-aggregates.ts``).
    """
    by_channel_map: Dict[str, dict] = params.get("byChannelMap") or {}
    latency_totals: dict = params.get("latencyTotals") or {}
    daily_latency_map: Dict[str, dict] = params.get("dailyLatencyMap") or {}
    model_daily_map: Dict[str, dict] = params.get("modelDailyMap") or {}
    daily_map: Dict[str, dict] = params.get("dailyMap") or {}

    by_channel = sorted(
        ({"channel": ch, "totals": t} for ch, t in by_channel_map.items()),
        key=lambda x: x["totals"].get("totalCost", 0),
        reverse=True,
    )
    latency = None
    if latency_totals.get("count", 0) > 0:
        latency = {
            "count": latency_totals["count"],
            "avgMs": latency_totals["sum"] / latency_totals["count"],
            "minMs": 0 if latency_totals.get("min") == math.inf else latency_totals["min"],
            "maxMs": latency_totals["max"],
            "p95Ms": latency_totals.get("p95Max", 0),
        }
    daily_latency = [
        {
            "date": entry["date"],
            "count": entry["count"],
            "avgMs": (entry["sum"] / entry["count"]) if entry["count"] else 0,
            "minMs": 0 if entry["min"] == math.inf else entry["min"],
            "maxMs": entry["max"],
            "p95Ms": entry["p95Max"],
        }
        for entry in daily_latency_map.values()
    ]
    daily_latency.sort(key=lambda x: x["date"])
    model_daily = sorted(
        list(model_daily_map.values()),
        key=lambda x: (x["date"], -x["cost"]),
    )
    daily = sorted(daily_map.values(), key=lambda x: x["date"])
    return {
        "byChannel": by_channel,
        "latency": latency,
        "dailyLatency": daily_latency,
        "modelDaily": model_daily,
        "daily": daily,
    }


__all__ = [
    "merge_usage_latency",
    "merge_usage_daily_latency",
    "build_usage_aggregate_tail",
]
