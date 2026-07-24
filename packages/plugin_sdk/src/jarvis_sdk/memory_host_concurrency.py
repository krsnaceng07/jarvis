"""jarvis_sdk.memory_host_concurrency — bounded-concurrency runner.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/concurrency.ts`` (37 LOC).
Runs an array of async tasks with a bounded-concurrency
limit. The OpenClaw source uses ``p-map`` with
``stopOnError: true``; on failure, the runner drains the
in-flight tasks before re-raising.

Public API:
- ``run_with_concurrency(tasks, limit)`` — returns a list of
  results (one per task, in input order). Raises the first
  task's exception after draining in-flight tasks.

Key port decisions:
- We use ``asyncio.Semaphore`` for backpressure (no
  ``p-map`` equivalent is available in stdlib).
- The ``stop_on_error`` semantics are preserved: as soon as
  a task fails, no new tasks are admitted, in-flight tasks
  are awaited, and the original error is re-raised.
- Order is preserved (results are returned in the same
  indices as the input tasks).
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


async def run_with_concurrency(
    tasks: list[Callable[[], Awaitable[T]]],
    limit: int,
) -> list[T]:
    """Run ``tasks`` with bounded concurrency, stop-and-drain on error.

    Mirrors OpenClaw's ``runWithConcurrency``. The
    ``stopOnError`` semantics match the source: the first
    task to raise an exception cancels admission of new
    tasks; in-flight tasks are awaited (drained) before the
    exception is re-raised.

    Returns a list of results in the same order as ``tasks``.
    """
    bounded_limit = max(1, int(limit))
    semaphore = asyncio.Semaphore(bounded_limit)
    results: list[T | None] = [None] * len(tasks)
    first_error: BaseException | None = None
    in_flight: set[asyncio.Task[None]] = set()

    async def run_one(index: int, task: Callable[[], Awaitable[T]]) -> None:
        nonlocal first_error
        async with semaphore:
            if first_error is not None:
                return
            try:
                results[index] = await task()
            except BaseException as exc:  # noqa: BLE001 — mirror p-map's broad catch
                if first_error is None:
                    first_error = exc

    for index, task in enumerate(tasks):
        coro = run_one(index, task)
        in_flight.add(asyncio.create_task(coro))

    if not in_flight:
        return []

    # Wait for all tasks to finish (whether or not they raised);
    # gather absorbs individual exceptions so we can drain.
    await asyncio.gather(*in_flight, return_exceptions=True)

    if first_error is not None:
        raise first_error

    return [result for result in results if result is not None]


__all__ = ["run_with_concurrency"]
