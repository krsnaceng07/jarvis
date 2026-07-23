"""memory_core.time — small time helpers used across the dreaming pipeline.

OpenClaw parity: mirrors ``extensions/memory-core/src/time.ts``.

Two helpers:
- ``resolve_memory_core_now_ms`` — accept an optional ``nowMs`` (any
  type per OpenClaw's TS signature) and return a numeric millisecond
  timestamp. Falls back to ``Date.now()`` if input is not a number.
- ``resolve_memory_core_timestamp`` — same as above but returns an
  ISO-8601 string suitable for event timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from numbers import Real
from typing import Any


def resolve_memory_core_now_ms(now_ms: Any) -> int:
    """Return ``now_ms`` if it's numeric; else ``Date.now()``.

    Mirrors OpenClaw's ``resolveMemoryCoreNowMs``. Accepts ``unknown``
    (any Python value) and only treats real numbers as a valid input.
    """
    if isinstance(now_ms, Real) and not isinstance(now_ms, bool):
        return int(now_ms)  # type: ignore[arg-type]
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def resolve_memory_core_timestamp(now_ms: Any) -> str:
    """Return an ISO-8601 timestamp string.

    Mirrors OpenClaw's ``resolveMemoryCoreTimestamp``. If ``now_ms`` is
    numeric, use it; else fall back to the current UTC time.
    """
    if isinstance(now_ms, Real) and not isinstance(now_ms, bool):
        return datetime.fromtimestamp(int(now_ms) / 1000, tz=UTC).isoformat()  # type: ignore[arg-type]
    return datetime.now(tz=UTC).isoformat()


__all__ = ["resolve_memory_core_now_ms", "resolve_memory_core_timestamp"]
