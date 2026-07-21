"""jarvis_sdk.retry_runtime — async retry with backoff.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/retry-runtime``'s ``retryAsync``.

Used by ``memory-wiki`` to retry the transient
"concurrent-rewrite race" guard failure during vault
page writes. OpenClaw uses a short bounded retry with
linear backoff to close a sub-millisecond window; the
Python port preserves that shape.

Parity
======
- ``retry_async(fn, options)`` → ``Any`` (the result of
  the eventual successful attempt). Raises the last
  caught exception on exhaustion. ``attempts`` defaults
  to ``3``; ``min_delay_ms`` / ``max_delay_ms`` clamp the
  per-attempt delay to a positive integer ms. The
  ``should_retry`` predicate filters which exceptions
  are retryable; everything else propagates immediately.
"""

from __future__ import annotations

import asyncio
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def retry_async(
    fn: Callable[[], Awaitable[Any]],
    options: dict[str, Any] | None = None,
) -> Any:
    """Run ``fn`` with bounded retry.

    Mirrors ``openclaw/plugin-sdk/retry-runtime``'s
    ``retryAsync``. ``options`` keys:
    - ``attempts`` (int, default 3): total attempts.
    - ``minDelayMs`` (int, default 25): floor for the
      per-attempt backoff.
    - ``maxDelayMs`` (int, default 100): ceiling for the
      per-attempt backoff.
    - ``label`` (str, optional): used in the trace log.
    - ``shouldRetry`` (callable, optional): predicate
      ``(error) -> bool``; only retry when it returns
      True. Defaults to retry on any exception.

    Returns the result of the first successful attempt.
    Raises the last exception when all attempts fail.
    """
    options = options or {}
    attempts = max(1, int(options.get("attempts", 3) or 3))
    min_delay_ms = max(0, int(options.get("minDelayMs", 25) or 25))
    max_delay_ms = max(min_delay_ms, int(options.get("maxDelayMs", 100) or 100))
    should_retry = options.get("shouldRetry")

    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except BaseException as exc:
            last_exc = exc
            if should_retry is not None and not should_retry(exc):
                raise
            if attempt + 1 >= attempts:
                raise
            # Linear backoff with a small jitter to avoid
            # lockstep retries from a herd of writers.
            spread = max(0, max_delay_ms - min_delay_ms)
            jitter = secrets.randbelow(spread + 1) if spread > 0 else 0
            delay = min_delay_ms + jitter
            await asyncio.sleep(delay / 1000.0)
    # Unreachable, but keep mypy / pyright happy.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry_async exhausted with no captured exception")


__all__ = ["retry_async"]
