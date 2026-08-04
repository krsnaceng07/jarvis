"""jarvis.config.cron_limits — cron scheduling limit defaults.

OpenClaw parity: mirrors ``openclaw-main/src/config/cron-limits.ts``.
"""
from __future__ import annotations

from typing import Optional


DEFAULT_CRON_MAX_CONCURRENT_RUNS = 8
DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS = 30_000


def resolve_cron_max_concurrent_runs(cron_config: Optional[dict] = None) -> int:
    """Resolve cron concurrency config.

    Mirrors :func:`resolveCronMaxConcurrentRuns`
    (``shared/config/cron-limits.ts``).
    """
    raw = (cron_config or {}).get("maxConcurrentRuns")
    if isinstance(raw, (int, float)) and raw == raw and raw != float("inf"):
        return max(1, int(raw))
    return DEFAULT_CRON_MAX_CONCURRENT_RUNS


def resolve_cron_trigger_min_interval_ms(cron_config: Optional[dict] = None) -> int:
    """Resolve the minimum cadence for trigger-bearing cron jobs.

    Mirrors :func:`resolveCronTriggerMinIntervalMs`
    (``shared/config/cron-limits.ts``).
    """
    raw = (cron_config or {}).get("triggers", {}).get("minIntervalMs")
    if isinstance(raw, (int, float)) and raw == raw and raw != float("inf"):
        return max(1, int(raw))
    return DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS


__all__ = [
    "DEFAULT_CRON_MAX_CONCURRENT_RUNS",
    "DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS",
    "resolve_cron_max_concurrent_runs",
    "resolve_cron_trigger_min_interval_ms",
]
