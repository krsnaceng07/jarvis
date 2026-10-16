"""jarvis.utils.with_timeout — re-export of the shared timeout helper.

OpenClaw parity: mirrors ``openclaw-main/src/utils/with-timeout.ts``.

Public surface:

- :func:`with_timeout`
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Optional, TypeVar

T = TypeVar("T")


async def with_timeout(
    promise: Awaitable[T],
    timeout_ms: int,
    *,
    timeout_error: Optional[BaseException] = None,
) -> T:
    """Await ``promise`` with a millisecond timeout.

    Mirrors :func:`withTimeout` (``utils/with-timeout.ts`` → ``infra/fs-safe.ts``).
    """
    if timeout_ms <= 0:
        return await promise
    try:
        return await asyncio.wait_for(promise, timeout=timeout_ms / 1000.0)
    except asyncio.TimeoutError as exc:
        if timeout_error is not None:
            raise timeout_error from exc
        raise


__all__ = ["with_timeout"]
