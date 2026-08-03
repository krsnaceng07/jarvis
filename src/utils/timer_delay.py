"""jarvis.utils.timer_delay — timer delay helpers clamped to runtime-safe values.

OpenClaw parity: mirrors ``openclaw-main/src/utils/timer-delay.ts``.

Public surface:

- :data:`MAX_SAFE_TIMEOUT_DELAY_MS`
- :func:`resolve_safe_timeout_delay_ms`
- :func:`add_safe_timeout_delay_grace_ms`
- :func:`set_safe_timeout`
"""
from __future__ import annotations

from typing import Any, Optional


#: Cap any timeout delay at 1 hour by default.
MAX_SAFE_TIMEOUT_DELAY_MS = 60 * 60 * 1000

#: Minimum allowed delay (negative or NaN → 0).
_MIN_SAFE_TIMEOUT_DELAY_MS = 0


def resolve_safe_timeout_delay_ms(
    value: Any,
    opts: Optional[dict] = None,
) -> int:
    """Clamp ``value`` into the runtime-safe [0, MAX] range.

    Mirrors :func:`resolveSafeTimeoutDelayMs` (``utils/timer-delay.ts``).
    """
    opts = opts or {}
    min_ms = int(opts.get("minMs", _MIN_SAFE_TIMEOUT_DELAY_MS)) if isinstance(opts, dict) else 0
    try:
        n = int(value)
    except (TypeError, ValueError):
        return min_ms
    if n != n:  # NaN
        return min_ms
    if n < min_ms:
        return min_ms
    if n > MAX_SAFE_TIMEOUT_DELAY_MS:
        return MAX_SAFE_TIMEOUT_DELAY_MS
    return n


def add_safe_timeout_delay_grace_ms(value: int, grace_ms: int = 0) -> int:
    """Add a small grace margin to a timeout, clamped to the safe max.

    Mirrors :func:`addSafeTimeoutDelayGraceMs` (``utils/timer-delay.ts``).
    """
    try:
        grace = int(grace_ms or 0)
    except (TypeError, ValueError):
        grace = 0
    return resolve_safe_timeout_delay_ms(int(value or 0) + grace)


def set_safe_timeout(
    callback: Any, delay_ms: int, opts: Optional[dict] = None
) -> Any:
    """Wrap :func:`threading.Timer` (or asyncio call_later) with safe clamping.

    Mirrors :func:`setSafeTimeout` (``utils/timer-delay.ts``).
    """
    safe = resolve_safe_timeout_delay_ms(delay_ms, opts)
    try:
        # Default: use threading.Timer so the helper is sync and side-effect free.
        import threading

        return threading.Timer(safe / 1000.0, callback)
    except Exception:
        return None


__all__ = [
    "MAX_SAFE_TIMEOUT_DELAY_MS",
    "resolve_safe_timeout_delay_ms",
    "add_safe_timeout_delay_grace_ms",
    "set_safe_timeout",
]
