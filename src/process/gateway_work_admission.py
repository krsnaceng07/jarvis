"""jarvis.process.gateway_work_admission — coordinates process-wide root work admission.

OpenClaw parity: mirrors ``src/process/gateway-work-admission.ts``.

Provides process-level work admission, host suspension gating, and restart draining.
Uses ``contextvars.ContextVar`` as the Python equivalent of Node's ``AsyncLocalStorage``
to track active request context across asyncio tasks.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

log = logging.getLogger("jarvis.process.gateway_work_admission")


class GatewayDrainingError(Exception):
    """Raised when work is rejected because the gateway is draining for restart.

    Mirrors ``GatewayDrainingError``.
    """

    def __init__(self) -> None:
        super().__init__("Gateway is draining; new tasks are not accepted")


@dataclass(eq=False)
class GatewayRootWorkAdmission:
    references: int = 1
    released: bool = False


_current_root_work: contextvars.ContextVar[GatewayRootWorkAdmission | None] = (
    contextvars.ContextVar("_current_root_work", default=None)
)


@dataclass
class _WorkAdmissionState:
    restart_draining: bool = False
    restart_signal_pending: bool = False
    restart_signal_generation: int = 0
    suspend_phase: str = "accepting"  # "accepting" | "preparing" | "prepared"
    suspend_generation: int = 0
    suspend_invalidated: Callable[[], None] | None = None
    active_root_work: set[GatewayRootWorkAdmission] = field(default_factory=set)
    root_drain_waiters: set[asyncio.Future[None]] = field(default_factory=set)
    suspend_open_waiters: set[asyncio.Future[None]] = field(default_factory=set)


_state = _WorkAdmissionState()


def _log_admission_closed(reason: str) -> None:
    log.info("admission closed: %s", reason)


def _log_admission_reopened(reason: str) -> None:
    log.info("admission reopened: %s", reason)


def _resolve_root_drain_waiters() -> None:
    waiters = list(_state.root_drain_waiters)
    _state.root_drain_waiters.clear()
    for fut in waiters:
        if not fut.done():
            fut.set_result(None)


def _resolve_suspend_open_waiters() -> None:
    waiters = list(_state.suspend_open_waiters)
    _state.suspend_open_waiters.clear()
    for fut in waiters:
        if not fut.done():
            fut.set_result(None)


def _invalidate_suspend_admission() -> None:
    callback = _state.suspend_invalidated
    was_closed = _state.suspend_phase != "accepting"
    _state.suspend_invalidated = None
    _state.suspend_phase = "accepting"
    _state.suspend_generation += 1
    _resolve_suspend_open_waiters()
    if was_closed and not _state.restart_draining:
        _log_admission_reopened("suspend phase")
    if callback:
        try:
            callback()
        except Exception:
            log.exception("Error in suspend invalidated callback")


def _clear_restart_signal_fence() -> bool:
    if _state.restart_draining or not _state.restart_signal_pending:
        return False
    _state.restart_signal_pending = False
    _state.restart_signal_generation += 1
    _resolve_suspend_open_waiters()
    _log_admission_reopened("restart-signal fence")
    return True


@dataclass
class GatewayRootWorkAdmissionLease:
    owns_root: bool
    release_fn: Callable[[], None]
    admission: GatewayRootWorkAdmission | None = None

    def release(self) -> None:
        self.release_fn()

    async def run(self, fn: Callable[[], Awaitable[T]]) -> T:
        if self.admission is None:
            return await fn()
        token = _current_root_work.set(self.admission)
        try:
            return await fn()
        finally:
            _current_root_work.reset(token)


@dataclass
class GatewaySuspendAdmissionLease:
    commit_fn: Callable[[], bool]
    rollback_fn: Callable[[], bool]
    release_fn: Callable[[], bool]

    def commit(self) -> bool:
        return self.commit_fn()

    def rollback(self) -> bool:
        return self.rollback_fn()

    def release(self) -> bool:
        return self.release_fn()


@dataclass
class GatewayRestartSignalAdmissionLease:
    rollback_fn: Callable[[], bool]

    def rollback(self) -> bool:
        return self.rollback_fn()


def _create_gateway_root_work_release(admission: GatewayRootWorkAdmission) -> Callable[[], None]:
    lease_released = False

    def release() -> None:
        nonlocal lease_released
        if lease_released or admission.released:
            return
        lease_released = True
        admission.references -= 1
        if admission.references > 0:
            return
        admission.released = True
        _state.active_root_work.discard(admission)
        if len(_state.active_root_work) == 0:
            _resolve_root_drain_waiters()

    return release


def _create_gateway_root_work_admission() -> GatewayRootWorkAdmissionLease:
    admission = GatewayRootWorkAdmission(references=1, released=False)
    _state.active_root_work.add(admission)
    release = _create_gateway_root_work_release(admission)
    return GatewayRootWorkAdmissionLease(
        owns_root=True,
        release_fn=release,
        admission=admission,
    )


# ---------------------------------------------------------------------------
# Public Inspection Functions
# ---------------------------------------------------------------------------


def is_gateway_work_admission_closed() -> bool:
    """Return True if restart signal/drain or host suspension rejects new work."""
    return (
        _state.restart_draining
        or _state.restart_signal_pending
        or _state.suspend_phase != "accepting"
    )


def is_gateway_subordinate_work_admission_closed() -> bool:
    """Return True if subordinate work admission is closed."""
    if _state.restart_draining or _state.restart_signal_pending:
        return True
    current = _current_root_work.get()
    if current is not None:
        return current.released
    return _state.suspend_phase != "accepting"


def get_gateway_suspend_admission_phase() -> str:
    """Return current suspend admission phase ('accepting', 'preparing', 'prepared')."""
    return _state.suspend_phase


def is_gateway_restart_draining() -> bool:
    """Return True if restart draining or signal is pending."""
    return _state.restart_draining or _state.restart_signal_pending


def mark_gateway_restart_draining() -> None:
    """Mark gateway as draining for restart (one-way)."""
    if _state.restart_draining:
        return
    _state.restart_signal_pending = False
    _state.restart_signal_generation += 1
    _state.restart_draining = True
    _resolve_suspend_open_waiters()
    _log_admission_closed("restart drain")
    if _state.suspend_phase != "accepting":
        _invalidate_suspend_admission()


def begin_gateway_restart_signal_admission() -> GatewayRestartSignalAdmissionLease | None:
    """Acquire restart signal fence."""
    if _state.restart_draining or _state.restart_signal_pending:
        return None
    _state.restart_signal_pending = True
    _state.restart_signal_generation += 1
    gen = _state.restart_signal_generation
    _log_admission_closed("restart-signal fence")

    def rollback() -> bool:
        if not _state.restart_signal_pending or _state.restart_signal_generation != gen:
            return False
        return _clear_restart_signal_fence()

    return GatewayRestartSignalAdmissionLease(rollback_fn=rollback)


def rollback_gateway_restart_signal_fence() -> bool:
    """Reopen restart signal fence."""
    return _clear_restart_signal_fence()


def try_begin_gateway_root_work_admission() -> GatewayRootWorkAdmissionLease | None:
    """Try to begin root work admission."""
    current = _current_root_work.get()
    if current is not None and not current.released:
        return GatewayRootWorkAdmissionLease(
            owns_root=False,
            release_fn=lambda: None,
            admission=None,
        )
    if (
        _state.restart_draining
        or _state.restart_signal_pending
        or _state.suspend_phase != "accepting"
    ):
        return None
    return _create_gateway_root_work_admission()


def try_begin_gateway_independent_root_work_admission() -> GatewayRootWorkAdmissionLease | None:
    """Try to begin independent root work admission."""
    if (
        _state.restart_draining
        or _state.restart_signal_pending
        or _state.suspend_phase != "accepting"
    ):
        return None
    return _create_gateway_root_work_admission()


async def begin_gateway_root_work_admission_when_open() -> GatewayRootWorkAdmissionLease:
    """Wait for admission to open, then acquire root work admission lease."""
    loop = asyncio.get_running_loop()
    while True:
        if _state.restart_draining:
            raise GatewayDrainingError()
        admission = try_begin_gateway_root_work_admission()
        if admission is not None:
            return admission
        fut: asyncio.Future[None] = loop.create_future()
        _state.suspend_open_waiters.add(fut)
        await fut


async def run_with_gateway_independent_root_work_admission(
    fn: Callable[[], Awaitable[T]],
) -> T:
    """Run fn with an independent root work admission lease."""
    loop = asyncio.get_running_loop()
    while True:
        if _state.restart_draining:
            raise Exception("gateway is draining for restart")
        admission = try_begin_gateway_independent_root_work_admission()
        if admission is not None:
            try:
                return await admission.run(fn)
            finally:
                admission.release()
        fut: asyncio.Future[None] = loop.create_future()
        _state.suspend_open_waiters.add(fut)
        await fut


def run_with_gateway_independent_root_work_continuation(
    fn: Callable[[], Awaitable[T]],
) -> Awaitable[T]:
    """Run fn with independent root work continuation."""
    parent = _current_root_work.get()
    if parent is None or parent.released:
        return run_with_gateway_independent_root_work_admission(fn)
    admission = _create_gateway_root_work_admission()

    async def wrapper() -> T:
        try:
            return await admission.run(fn)
        finally:
            admission.release()

    return wrapper()


def retain_gateway_root_work_admission_continuation() -> Callable[[], None] | None:
    """Retain continuation for current root work."""
    current = _current_root_work.get()
    if current is None or current.released:
        return None
    current.references += 1
    return _create_gateway_root_work_release(current)


def run_outside_gateway_root_work_admission(fn: Callable[[], T]) -> T:
    """Run function outside root work admission context."""
    token = _current_root_work.set(None)
    try:
        return fn()
    finally:
        _current_root_work.reset(token)


def get_active_gateway_root_work_count(*, exclude_current: bool = False) -> int:
    """Return active root work count."""
    count = len(_state.active_root_work)
    current = _current_root_work.get()
    if exclude_current and current is not None and not current.released and current in _state.active_root_work:
        count -= 1
    return max(0, count)


async def wait_for_active_gateway_root_work(
    timeout_ms: float | None = None,
) -> dict[str, Any]:
    """Wait for all active root work to drain."""
    if len(_state.active_root_work) == 0:
        return {"drained": True, "active": 0}
    if timeout_ms is not None and timeout_ms <= 0:
        return {"drained": False, "active": len(_state.active_root_work)}

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[None] = loop.create_future()
    _state.root_drain_waiters.add(fut)

    try:
        if timeout_ms is not None and timeout_ms > 0:
            await asyncio.wait_for(fut, timeout=timeout_ms / 1000.0)
        else:
            await fut
    except asyncio.TimeoutError:
        pass
    finally:
        _state.root_drain_waiters.discard(fut)

    active = len(_state.active_root_work)
    return {"drained": active == 0, "active": active}


def try_begin_gateway_suspend_admission(
    on_invalidated: Callable[[], None],
) -> GatewaySuspendAdmissionLease | None:
    """Try to begin suspend admission."""
    if (
        _state.restart_draining
        or _state.restart_signal_pending
        or _state.suspend_phase != "accepting"
    ):
        return None
    _state.suspend_phase = "preparing"
    _state.suspend_generation += 1
    gen = _state.suspend_generation
    _state.suspend_invalidated = on_invalidated
    _log_admission_closed("suspend phase")

    def transition(expected: str, next_phase: str) -> bool:
        if _state.suspend_generation != gen or _state.suspend_phase != expected:
            return False
        _state.suspend_phase = next_phase
        if next_phase == "accepting":
            _state.suspend_invalidated = None
            _resolve_suspend_open_waiters()
            _log_admission_reopened("suspend phase")
        return True

    return GatewaySuspendAdmissionLease(
        commit_fn=lambda: transition("preparing", "prepared"),
        rollback_fn=lambda: transition("preparing", "accepting"),
        release_fn=lambda: transition("prepared", "accepting"),
    )


def reset_gateway_work_admission() -> None:
    """Reset work admission state (for testing or reset)."""
    for admission in list(_state.active_root_work):
        admission.references = 0
        admission.released = True
    _state.active_root_work.clear()
    _resolve_root_drain_waiters()
    _state.restart_draining = False
    _state.restart_signal_pending = False
    _state.restart_signal_generation += 1
    if _state.suspend_phase != "accepting":
        _invalidate_suspend_admission()
    else:
        _state.suspend_generation += 1
        _state.suspend_invalidated = None
    _resolve_suspend_open_waiters()


__all__ = [
    "GatewayDrainingError",
    "GatewayRestartSignalAdmissionLease",
    "GatewayRootWorkAdmission",
    "GatewayRootWorkAdmissionLease",
    "GatewaySuspendAdmissionLease",
    "begin_gateway_restart_signal_admission",
    "begin_gateway_root_work_admission_when_open",
    "get_active_gateway_root_work_count",
    "get_gateway_suspend_admission_phase",
    "is_gateway_restart_draining",
    "is_gateway_subordinate_work_admission_closed",
    "is_gateway_work_admission_closed",
    "mark_gateway_restart_draining",
    "reset_gateway_work_admission",
    "retain_gateway_root_work_admission_continuation",
    "rollback_gateway_restart_signal_fence",
    "run_outside_gateway_root_work_admission",
    "run_with_gateway_independent_root_work_admission",
    "run_with_gateway_independent_root_work_continuation",
    "try_begin_gateway_independent_root_work_admission",
    "try_begin_gateway_root_work_admission",
    "try_begin_gateway_suspend_admission",
    "wait_for_active_gateway_root_work",
]
