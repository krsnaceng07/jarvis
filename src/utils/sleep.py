"""jarvis.utils.sleep — promise-based sleep with timer-input clamping.

OpenClaw parity: mirrors ``openclaw-main/src/utils/sleep.ts``.

Public surface:

- :func:`sleep`
"""
from __future__ import annotations

import asyncio


def _resolve_timer_timeout_ms(value: int, default_min: int = 0, default_max: int = 0) -> int:
    """Best-effort clamp for timer inputs. Mirrors the shared resolver in OpenClaw."""
    if not isinstance(value, (int, float)) or value != value:
        return default_min if default_min > 0 else 0
    safe = int(value)
    if safe < 0:
        return 0
    if default_max and safe > default_max:
        return default_max
    return safe


async def sleep(ms: int) -> None:
    """Promise-based sleep that clamps timer inputs through the shared timeout resolver.

    Mirrors :func:`sleep` (``utils/sleep.ts``).
    """
    delay = _resolve_timer_timeout_ms(ms)
    if delay <= 0:
        return
    await asyncio.sleep(delay / 1000.0)


__all__ = ["sleep", "_resolve_timer_timeout_ms"]
