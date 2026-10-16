"""jarvis.agents.sessions.tools.file_mutation_queue — per-file mutation queue.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/file-mutation-queue.ts``.

Phase 6.10c — per-file mutation queue.

Serializes edits/writes targeting the same
real file while allowing independent files
to mutate in parallel.

Adaptations
-----------
- The OpenClaw source uses
  ``KeyedAsyncQueue`` from
  ``openclaw/plugin-sdk/keyed-async-queue``.
  The Python port re-implements the
  keyed-async-queue locally with
  :mod:`asyncio.Lock` + a per-key dict.
- The OpenClaw source's ``realpathSync.native``
  is preserved (the Python equivalent is
  :func:`os.path.realpath`).
"""
from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


# ============================================================================
# KeyedAsyncQueue (re-implementation of the SDK class)
# ============================================================================


class _KeyedAsyncQueue:
    """Per-key async queue. Operations
    against the same key serialise; operations
    against different keys run in parallel.

    Mirrors ``KeyedAsyncQueue`` from
    ``openclaw/plugin-sdk/keyed-async-queue``.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def enqueue(
        self, key: str, fn: Callable[[], Awaitable[T]]
    ) -> T:
        lock = self._get_lock(key)
        async with lock:
            return await fn()


_file_mutation_queue = _KeyedAsyncQueue()


def _get_mutation_queue_key(file_path: str) -> str:
    """Resolve + realpath the file path so
    symlinks / relative segments all map to
    the same queue key. Mirrors
    ``getMutationQueueKey``
    (``file-mutation-queue.ts:12-19``)."""
    resolved = os.path.realpath(os.path.abspath(file_path))
    return resolved


async def with_file_mutation_queue(
    file_path: str, fn: Callable[[], Awaitable[T]]
) -> T:
    """Serialise file-mutation operations
    targeting ``file_path``. Operations
    against different paths run in parallel.
    Mirrors ``withFileMutationQueue``
    (``file-mutation-queue.ts:25-28``)."""
    key = _get_mutation_queue_key(file_path)
    return await _file_mutation_queue.enqueue(key, fn)


__all__ = [
    "with_file_mutation_queue",
]
