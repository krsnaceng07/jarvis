"""jarvis.shared.subagents_format — subagent format helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/subagents-format.ts``.
"""
from __future__ import annotations

import math
from typing import Optional


def _truncate_utf16_safe(value: str, max_length: int) -> str:
    if max_length <= 0:
        return ""
    if len(value) <= max_length:
        return value
    return value[:max_length]


def _format_token_short(value: Optional[float]) -> Optional[str]:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    n = int(value)
    if n < 1000:
        return f"{n}"
    if n < 10000:
        formatted = f"{n / 1000:.1f}"
        if formatted.endswith(".0"):
            formatted = formatted[:-2]
        return f"{formatted}k"
    if n < 1_000_000:
        thousands = round(n / 1000)
        # Rounding can reach 1000 — fall through to the million branch.
        if thousands < 1000:
            return f"{thousands}k"
    formatted = f"{n / 1_000_000:.1f}"
    if formatted.endswith(".0"):
        formatted = formatted[:-2]
    return f"{formatted}m"


def truncate_line(value: str, max_length: int) -> str:
    """Truncate a single-line display string without trailing whitespace.

    Mirrors :func:`truncateLine` (``shared/subagents-format.ts``).
    """
    limit = max(0, int(max_length))
    trimmed = value.rstrip() if isinstance(value, str) else ""
    if len(trimmed) <= limit:
        return trimmed
    marker = "..."
    if limit <= len(marker):
        return marker[:limit]
    return f"{_truncate_utf16_safe(trimmed, limit - len(marker)).rstrip()}{marker}"


def resolve_total_tokens(entry: Optional[dict]) -> Optional[float]:
    """Resolve total token usage, falling back to input+output.

    Mirrors :func:`resolveTotalTokens` (``shared/subagents-format.ts``).
    """
    if not entry or not isinstance(entry, dict):
        return None
    total = entry.get("totalTokens")
    if isinstance(total, (int, float)) and math.isfinite(total):
        return total
    inp = entry.get("inputTokens")
    out = entry.get("outputTokens")
    input_t = inp if isinstance(inp, (int, float)) else 0
    output_t = out if isinstance(out, (int, float)) else 0
    total_fallback = input_t + output_t
    return total_fallback if total_fallback > 0 else None


def _resolve_io_tokens(entry: Optional[dict]) -> Optional[dict]:
    if not entry or not isinstance(entry, dict):
        return None
    inp = entry.get("inputTokens")
    out = entry.get("outputTokens")
    input_t = inp if isinstance(inp, (int, float)) and math.isfinite(inp) else 0
    output_t = out if isinstance(out, (int, float)) and math.isfinite(out) else 0
    total = input_t + output_t
    if total <= 0:
        return None
    return {"input": input_t, "output": output_t, "total": total}


def format_token_usage_display(entry: Optional[dict]) -> str:
    """Format token usage for compact subagent list/detail displays.

    Mirrors :func:`formatTokenUsageDisplay` (``shared/subagents-format.ts``).
    """
    io = _resolve_io_tokens(entry)
    prompt_cache = resolve_total_tokens(entry)
    parts: list = []
    if io:
        in_str = _format_token_short(io["input"]) or "0"
        out_str = _format_token_short(io["output"]) or "0"
        parts.append(f"tokens {_format_token_short(io['total'])} (in {in_str} / out {out_str})")
    elif isinstance(prompt_cache, (int, float)) and prompt_cache > 0:
        parts.append(f"tokens {_format_token_short(prompt_cache)} prompt/cache")
    if isinstance(prompt_cache, (int, float)) and io and prompt_cache > io["total"]:
        parts.append(f"prompt/cache {_format_token_short(prompt_cache)}")
    return ", ".join(parts)


__all__ = [
    "truncate_line",
    "resolve_total_tokens",
    "format_token_usage_display",
]
