"""jarvis.shared.store_writer_queue — per-path FIFO store writer queue.

OpenClaw parity: mirrors ``openclaw-main/src/shared/store-writer-queue.ts``.

Focused minimal port: serializes writes per store path within one process.
The OpenClaw source uses ``AsyncLocalStorage`` to track reentrancy; the
Python port uses an explicit ``reentrant=True`` flag because Python's
``contextvars`` plumbing is caller-specific.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Awaitable, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")


class _StoreWriterTask:
    __slots__ = ("fn", "resolve", "reject")

    def __init__(self, fn, resolve, reject) -> None:
        self.fn = fn
        self.resolve = resolve
        self.reject = reject


class StoreWriterQueue:
    """Per-store-path FIFO queue that serializes file writes within one process."""

    def __init__(self) -> None:
        self.running = False
        self.pending: List[_StoreWriterTask] = []
        self.drain_promise: Optional[Awaitable[None]] = None


#: Per-path queue map (the "queues" param in OpenClaw).
StoreWriterQueues = Dict[str, StoreWriterQueue]

#: Tracks active reentrant writers per store path; OpenClaw uses
#: AsyncLocalStorage. Python contextvars need an explicit context object.
_active_writer: ContextVar[Optional[dict]] = ContextVar("active_store_writer", default=None)


def _is_active_store_writer(queues: StoreWriterQueues, store_path: str) -> bool:
    active = _active_writer.get()
    while active is not None:
        if active.get("active") and active.get("queues") is queues and active.get("storePath") == store_path:
            return True
        active = active.get("parent")
    return False


async def _run_active_store_writer(queues, store_path, fn):
    writer = {"active": True, "parent": _active_writer.get(), "queues": queues, "storePath": store_path}
    token = _active_writer.set(writer)
    try:
        return await fn()
    finally:
        writer["active"] = False
        _active_writer.reset(token)


def _get_or_create_store_writer_queue(queues, store_path):
    existing = queues.get(store_path)
    if existing is not None:
        return existing
    created = StoreWriterQueue()
    queues[store_path] = created
    return created


async def _drain_store_writer_queue(queues, store_path):
    queue = queues.get(store_path)
    if queue is None:
        return
    if queue.drain_promise is not None:
        await queue.drain_promise
        return
    queue.running = True

    async def _drain_loop():
        try:
            while queue.pending:
                task = queue.pending.pop(0)
                try:
                    result = await task.fn()
                except Exception as exc:
                    task.reject(exc)
                    continue
                task.resolve(result)
        finally:
            queue.running = False
            queue.drain_promise = None
            if not queue.pending:
                queues.pop(store_path, None)

    queue.drain_promise = _drain_loop()
    try:
        await queue.drain_promise
    except Exception:
        pass


async def run_queued_store_write(
    queues: StoreWriterQueues,
    store_path: str,
    label: str,
    fn: Callable[[], Awaitable[T]],
    reentrant: bool = False,
) -> T:
    """Run one store write after prior writes for the same store path finish.

    Mirrors :func:`runQueuedStoreWrite` (``shared/store-writer-queue.ts``).
    """
    if not isinstance(store_path, str) or not store_path:
        raise ValueError(
            f"{label}: storePath must be a non-empty string, got {store_path!r}"
        )
    if reentrant and _is_active_store_writer(queues, store_path):
        return await fn()
    queue = _get_or_create_store_writer_queue(queues, store_path)

    future: asyncio.Future = asyncio.get_event_loop().create_future()

    async def _task_body():
        return await _run_active_store_writer(queues, store_path, fn)

    queue.pending.append(
        _StoreWriterTask(
            fn=_task_body,
            resolve=lambda v: future.get_loop().call_soon_threadsafe(future.set_result, v)
                if not future.get_loop().is_closed() else None,
            reject=lambda e: future.get_loop().call_soon_threadsafe(future.set_exception, e)
                if not future.get_loop().is_closed() else None,
        )
    )
    drain_task = asyncio.create_task(_drain_store_writer_queue(queues, store_path))
    try:
        return await future
    finally:
        if not drain_task.done():
            await drain_task


def clear_store_writer_queues_for_test(queues: StoreWriterQueues, message: str) -> None:
    """Reject pending queued writes and clear queue state for test cleanup.

    Mirrors :func:`clearStoreWriterQueuesForTest`
    (``shared/store-writer-queue.ts``).
    """
    for queue in list(queues.values()):
        for task in queue.pending:
            task.reject(RuntimeError(message))
    queues.clear()


async def drain_store_writer_queues_for_test(
    queues: StoreWriterQueues, message: str
) -> None:
    """Wait for active drains while rejecting still-pending test writes.

    Mirrors :func:`drainStoreWriterQueuesForTest`
    (``shared/store-writer-queue.ts``).
    """
    while queues:
        active_queues = list(queues.values())
        for queue in active_queues:
            for task in queue.pending:
                task.reject(RuntimeError(message))
            queue.pending = []
        active_drains = [q.drain_promise for q in active_queues if q.drain_promise is not None]
        if not active_drains:
            queues.clear()
            return
        results = await asyncio.gather(*active_drains, return_exceptions=True)
        if not any(isinstance(r, Exception) for r in results):
            continue


__all__ = [
    "StoreWriterQueue",
    "StoreWriterQueues",
    "run_queued_store_write",
    "clear_store_writer_queues_for_test",
    "drain_store_writer_queues_for_test",
]
