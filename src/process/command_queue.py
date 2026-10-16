"""jarvis.process.command_queue — in-process command queue with lane concurrency.

OpenClaw parity: mirrors ``src/process/command-queue.ts``.

Serializes and limits process execution per named command lane.
Each lane has a ``max_concurrent`` slot and a FIFO/priority queue.
The gateway applier sets concurrency via ``set_command_lane_concurrency``;
the enqueue path reads the live concurrency before each dispatch.

Key design
----------
- Default lane (``main``) preserves serial execution.
- Additional lanes allow low-risk parallelism (cron, subagent) without
  interleaving main-workflow output.
- ``CommandLaneClearedError`` — raised when a queued task's lane is drained.
- ``enqueue_command`` — submit an async task to a named lane.
- ``drain_lane`` — cancel all queued (not yet started) work in a lane.
- ``get_lane_snapshot`` — introspect live queue state.

Public surface
--------------
``CommandLaneClearedError``
``CommandLaneTaskMarker``
``CommandLaneSnapshot``
``enqueue_command``
``drain_lane``
``get_lane_snapshot``
``get_all_lane_snapshots``
``set_command_lane_concurrency``   (re-exported from server_lanes)
``get_command_lane_concurrency``   (re-exported from server_lanes)
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from typing import Any, Awaitable, Callable

from src.gateway.server_lanes import (
    get_command_lane_concurrency,
    set_command_lane_concurrency,
)
from src.process.gateway_work_admission import (
    GatewayDrainingError,
    is_gateway_work_admission_closed,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CommandLaneClearedError(Exception):
    """Raised when a queued command is rejected because its lane was cleared.

    Mirrors ``CommandLaneClearedError``.
    """

    def __init__(self, lane: str | None = None) -> None:
        super().__init__(f'Command lane "{lane}" cleared' if lane else "Command lane cleared")
        self.lane = lane


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class CommandLaneTaskMarker:
    """Identifies a running task within its lane.

    Mirrors ``CommandLaneTaskMarker``.
    """

    lane: str
    task_id: int
    generation: int


@dataclasses.dataclass(frozen=True, slots=True)
class CommandLaneSnapshot:
    """Point-in-time view of one lane's state.

    Mirrors ``CommandLaneSnapshot``.
    """

    lane: str
    queued_count: int
    active_count: int
    max_concurrent: int
    draining: bool
    generation: int


# ---------------------------------------------------------------------------
# Internal lane state
# ---------------------------------------------------------------------------

_DEFAULT_MAX_CONCURRENT = 1
_DEFAULT_WARN_AFTER_MS = 30_000


@dataclasses.dataclass
class _QueueEntry:
    task: Callable[[CommandLaneTaskMarker], Awaitable[Any]]
    future: asyncio.Future[Any]
    enqueued_at: float  # monotonic seconds
    sequence: int
    priority: int = 0  # lower = higher priority in PQ (min-heap compat)


@dataclasses.dataclass
class _LaneState:
    lane: str
    queue: list[_QueueEntry] = dataclasses.field(default_factory=list)
    active_task_ids: set[int] = dataclasses.field(default_factory=set)
    max_concurrent: int = _DEFAULT_MAX_CONCURRENT
    draining: bool = False
    generation: int = 0


# Global lane registry (mirrors the globalThis singleton in OpenClaw).
_lanes: dict[str, _LaneState] = {}
_next_task_id: int = 1
_next_sequence: int = 1


def _get_or_create_lane(lane: str) -> _LaneState:
    if lane not in _lanes:
        # Inherit concurrency from server_lanes registry if set.
        saved = get_command_lane_concurrency(lane)
        _lanes[lane] = _LaneState(
            lane=lane,
            max_concurrent=saved if saved is not None else _DEFAULT_MAX_CONCURRENT,
        )
    return _lanes[lane]


# ---------------------------------------------------------------------------
# Concurrency sync from server_lanes
# ---------------------------------------------------------------------------
# Override set_command_lane_concurrency to also update live _LaneState objects.

_original_set = set_command_lane_concurrency


def _patched_set_concurrency(lane_id: str, limit: int) -> None:
    _original_set(lane_id, limit)
    if lane_id in _lanes:
        clamped = max(0, int(limit))
        _lanes[lane_id].max_concurrent = clamped
        # If concurrency was re-enabled, try to dispatch queued work.
        if clamped > 0:
            loop = _get_running_loop()
            if loop:
                loop.call_soon_threadsafe(lambda: _try_dispatch(lane_id))


def _get_running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# Re-export the patched version.
set_command_lane_concurrency = _patched_set_concurrency  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Dispatch engine
# ---------------------------------------------------------------------------


def _try_dispatch(lane_name: str) -> None:
    """Attempt to dispatch queued entries for *lane_name* if slots are free."""
    lane = _lanes.get(lane_name)
    if lane is None or lane.draining:
        return

    while lane.queue and len(lane.active_task_ids) < lane.max_concurrent:
        # Pop the highest-priority (lowest priority value) entry.
        entry = _pop_entry(lane)
        if entry is None:
            break

        if entry.future.cancelled() or entry.future.done():
            continue

        global _next_task_id
        task_id = _next_task_id
        _next_task_id += 1
        lane.active_task_ids.add(task_id)

        marker = CommandLaneTaskMarker(
            lane=lane_name,
            task_id=task_id,
            generation=lane.generation,
        )

        async def _run(entry: _QueueEntry = entry, tid: int = task_id, m: CommandLaneTaskMarker = marker) -> None:
            try:
                result = await entry.task(m)
                if not entry.future.done():
                    entry.future.set_result(result)
            except Exception as exc:
                if not entry.future.done():
                    entry.future.set_exception(exc)
            finally:
                lane.active_task_ids.discard(tid)
                _try_dispatch(lane_name)

        asyncio.ensure_future(_run())


def _pop_entry(lane: _LaneState) -> _QueueEntry | None:
    if not lane.queue:
        return None
    # Sort by (priority ASC, sequence ASC) — priority 0 = highest.
    lane.queue.sort(key=lambda e: (e.priority, e.sequence))
    return lane.queue.pop(0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enqueue_command(
    lane: str,
    task: Callable[[CommandLaneTaskMarker], Awaitable[Any]],
    *,
    priority: int = 0,
    warn_after_ms: int = _DEFAULT_WARN_AFTER_MS,
) -> Any:
    """Submit *task* to *lane* and await its result.

    Mirrors ``enqueueCommand``.

    ``priority`` follows min-heap semantics: lower integers run first.
    Raises :class:`GatewayDrainingError` if the gateway is draining/closed,
    or :class:`CommandLaneClearedError` if the lane is drained before task starts.
    """
    if is_gateway_work_admission_closed():
        raise GatewayDrainingError()

    global _next_sequence

    lane_state = _get_or_create_lane(lane)

    loop = asyncio.get_event_loop()
    future: asyncio.Future[Any] = loop.create_future()

    seq = _next_sequence
    _next_sequence += 1

    entry = _QueueEntry(
        task=task,
        future=future,
        enqueued_at=time.monotonic(),
        sequence=seq,
        priority=priority,
    )
    lane_state.queue.append(entry)
    _try_dispatch(lane)

    return await future


def drain_lane(lane: str) -> int:
    """Cancel all queued (not yet active) entries in *lane*.

    Mirrors ``drainCommandLane``.
    Returns the number of entries cancelled.
    """
    lane_state = _lanes.get(lane)
    if lane_state is None:
        return 0

    lane_state.draining = True
    lane_state.generation += 1
    cancelled = 0
    for entry in lane_state.queue:
        if not entry.future.done():
            entry.future.set_exception(CommandLaneClearedError(lane))
            cancelled += 1
    lane_state.queue.clear()
    lane_state.draining = False
    return cancelled


def get_lane_snapshot(lane: str) -> CommandLaneSnapshot | None:
    """Return a point-in-time snapshot of *lane*, or None if unknown.

    Mirrors ``getCommandLaneSnapshot``.
    """
    lane_state = _lanes.get(lane)
    if lane_state is None:
        return None
    return CommandLaneSnapshot(
        lane=lane,
        queued_count=len(lane_state.queue),
        active_count=len(lane_state.active_task_ids),
        max_concurrent=lane_state.max_concurrent,
        draining=lane_state.draining,
        generation=lane_state.generation,
    )


def get_all_lane_snapshots() -> list[CommandLaneSnapshot]:
    """Return snapshots of all registered lanes, sorted by lane name."""
    return [
        CommandLaneSnapshot(
            lane=ls.lane,
            queued_count=len(ls.queue),
            active_count=len(ls.active_task_ids),
            max_concurrent=ls.max_concurrent,
            draining=ls.draining,
            generation=ls.generation,
        )
        for ls in sorted(_lanes.values(), key=lambda s: s.lane)
    ]


def reset_command_queue_for_test() -> None:
    """Clear all lane state. For use in tests only."""
    _lanes.clear()
    global _next_task_id, _next_sequence
    _next_task_id = 1
    _next_sequence = 1


__all__ = [
    "CommandLaneClearedError",
    "CommandLaneSnapshot",
    "CommandLaneTaskMarker",
    "GatewayDrainingError",
    "drain_lane",
    "enqueue_command",
    "get_all_lane_snapshots",
    "get_command_lane_concurrency",
    "get_lane_snapshot",
    "reset_command_queue_for_test",
    "set_command_lane_concurrency",
]
