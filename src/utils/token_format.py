"""jarvis.utils.token_format — token count formatting helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/token-format.ts``.

Public surface:

- :func:`format_token_count`
"""
from __future__ import annotations

import math
from typing import Optional


def format_token_count(value: Optional[float]) -> str:
    """Format a token count for compact human-facing status text.

    Mirrors :func:`formatTokenCount` (``utils/token-format.ts``).
    """
    if value is None or not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value):
        return "0"
    safe = max(0, value)
    if safe >= 1_000_000:
        return f"{safe / 1_000_000:.1f}m"
    if safe >= 1_000:
        precision = 0 if safe >= 10_000 else 1
        formatted_thousands = f"{safe / 1_000:.{precision}f}"
        if float(formatted_thousands) >= 1_000:
            return f"{safe / 1_000_000:.1f}m"
        return f"{formatted_thousands}k"
    return str(int(round(safe)))


__all__ = ["format_token_count"]
