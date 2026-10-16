"""jarvis.shared.string_sample — bounded string-entry summarizer.

OpenClaw parity: mirrors ``openclaw-main/src/shared/string-sample.ts``.
"""
from __future__ import annotations

import math


def summarize_string_entries(params: dict) -> str:
    """Format a bounded comma-separated sample with a hidden-count suffix.

    Mirrors :func:`summarizeStringEntries` (``shared/string-sample.ts``).
    """
    entries = params.get("entries") or []
    if len(entries) == 0:
        return params.get("emptyText") or ""
    raw_limit = params.get("limit")
    if raw_limit is None:
        raw_limit = 6
    # Keep summaries useful for operator output even when callers pass bad limits.
    if isinstance(raw_limit, (int, float)) and math.isfinite(raw_limit):
        limit = max(1, int(raw_limit))
    else:
        limit = 6
    sample = list(entries[:limit])
    suffix = f" (+{len(entries) - len(sample)})" if len(entries) > len(sample) else ""
    return f"{', '.join(sample)}{suffix}"


__all__ = ["summarize_string_entries"]
