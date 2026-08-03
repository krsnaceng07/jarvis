"""jarvis.shared.deferred — Promise-style deferred resolvers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/deferred.ts``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class Deferred(Generic[T]):
    """A promise with externally-callable resolve/reject.

    Mirrors :type:`Deferred` (``shared/deferred.ts``).
    """
    promise: Awaitable[T]
    resolve: Callable[[object], None]
    reject: Callable[[object], None]


def create_deferred() -> Deferred[None]:
    """Create a :class:`Deferred` that can be resolved/rejected externally.

    Mirrors :func:`createDeferred` (``shared/deferred.ts``).
    """
    holder: dict = {}

    def _resolve(value: object) -> None:
        # Python asyncio.Future-like resolve is async; this Python port uses a
        # synchronous sentinel because the surface in OpenClaw is a
        # Promise + resolve/reject pair that callers can drive from any
        # awaitable context.
        holder.setdefault("resolved", value)

    def _reject(reason: object) -> None:
        holder.setdefault("rejected", reason)

    async def _promise() -> None:
        while True:
            if "resolved" in holder:
                return holder["resolved"]
            if "rejected" in holder:
                raise holder["rejected"]
            # Yield to event loop briefly so callers have a chance to settle.
            import asyncio
            await asyncio.sleep(0)

    return Deferred(promise=_promise(), resolve=_resolve, reject=_reject)


__all__ = ["Deferred", "create_deferred"]
