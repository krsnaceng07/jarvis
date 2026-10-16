"""jarvis.utils.usage_format — usage / cost formatting helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/usage-format.ts``.

Public surface:

- :func:`format_usage_cost_usd`
- :func:`format_usage_tokens`

Phase 8.1 — focused minimal port of OpenClaw ``usage-format.ts``.
"""
from __future__ import annotations

import math
from typing import Any


# Installable hooks ---------------------------------------------------------

_format_usage_cost_usd_hook = None
_format_usage_tokens_hook = None


def set_format_usage_cost_usd_hook(fn) -> None:
    global _format_usage_cost_usd_hook
    _format_usage_cost_usd_hook = fn


def set_format_usage_tokens_hook(fn) -> None:
    global _format_usage_tokens_hook
    _format_usage_tokens_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _format_compact_number(value: float, precision: int = 2) -> str:
    if value == 0:
        return "0"
    if abs(value) < 0.01:
        return f"{value:.4f}"
    if abs(value) < 1:
        return f"{value:.{precision}f}"
    if abs(value) < 1000:
        return f"{value:.2f}"
    if abs(value) < 1_000_000:
        return f"{value / 1_000:.2f}K"
    if abs(value) < 1_000_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value / 1_000_000_000:.2f}B"


def format_usage_cost_usd(value: Any) -> str:
    """Format a USD cost value as a compact, human-readable string.

    Mirrors :func:`formatUsageCostUsd` (``utils/usage-format.ts``).
    """
    if _format_usage_cost_usd_hook is not None:
        v = _format_usage_cost_usd_hook(value)
        return v if isinstance(v, str) else ""
    if isinstance(value, bool) or value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(amount) or math.isinf(amount):
        return ""
    sign = "-" if amount < 0 else ""
    abs_amount = abs(amount)
    if abs_amount == 0:
        return "$0.00"
    if abs_amount < 0.01:
        return f"{sign}${abs_amount:.4f}"
    if abs_amount < 1:
        return f"{sign}${abs_amount:.{3 if abs_amount < 0.1 else 2}f}"
    if abs_amount < 100:
        return f"{sign}${abs_amount:.2f}"
    return f"{sign}${_format_compact_number(abs_amount)}"


def format_usage_tokens(value: Any) -> str:
    """Format a token count for compact human-facing status text.

    Mirrors :func:`formatUsageTokens` (``utils/usage-format.ts``).
    """
    if _format_usage_tokens_hook is not None:
        v = _format_usage_tokens_hook(value)
        return v if isinstance(v, str) else ""
    if isinstance(value, bool) or value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(amount) or math.isinf(amount):
        return ""
    if amount < 0:
        return ""
    if amount < 1000:
        return str(int(amount))
    if amount < 1_000_000:
        if amount < 10_000:
            return f"{amount / 1000:.1f}K"
        return f"{int(amount / 1000)}K"
    if amount < 1_000_000_000:
        if amount < 10_000_000:
            return f"{amount / 1_000_000:.1f}M"
        return f"{int(amount / 1_000_000)}M"
    return f"{amount / 1_000_000_000:.1f}B"


__all__ = [
    "format_usage_cost_usd",
    "format_usage_tokens",
    "set_format_usage_cost_usd_hook",
    "set_format_usage_tokens_hook",
]
