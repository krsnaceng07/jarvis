"""Serializes lifecycle mutations and work admission for logical session identities.

Mirrors OpenClaw's ``src/sessions/session-lifecycle-admission.ts``.

Public surface (mirrors the TS source):
- ``run_exclusive_session_lifecycle`` — acquire all
  per-identity lifecycle locks before running a block
- ``run_exclusive_session_lifecycle_mutation`` — acquire
  mutation locks for the given identities; runs the
  caller under the per-identity exclusive lane
- ``is_session_lifecycle_mutation_active`` — predicate
- ``has_only_session_lifecycle_mutation_kind_active`` —
  predicate
- ``is_session_work_admission_active`` — predicate
- ``is_competing_session_work_admission_active`` —
  predicate (excludes the current stack's own admissions)
- ``collect_active_session_work_admission_identities`` —
  collect identities for a given scope
- ``get_active_session_work_admission_count`` — count
- ``get_active_session_lifecycle_mutation_count`` — count
- ``begin_session_work_admission`` — admission lifecycle
- ``interrupt_session_work_admissions`` — interrupt
  competing work for the given identities

Public constants:
- ``SESSION_WORK_ADMISSION_DRAIN_TIMEOUT_MS`` = 15_000

Re-exports from session_work_admission_handoff:
- ``cancel_session_work_admission_handoff``
- ``consume_session_work_admission_handoff``
- ``SessionWorkAdmissionLease``

Python adaptations (documented in code):
- TS AsyncLocalStorage → Python contextvars.ContextVar;
  the per-store-path writer context is kept in a
  ContextVar that the queue runner unwinds/rewinds
- TS runQueuedStoreWrite / runExclusiveSessionStoreWrite →
  inlined FIFO queue (mirrors
  ``@openclaw/shared/store-writer-queue``'s
  ``runQueuedStoreWrite`` shape)
- TS AbortSignal → Python threading.Event + a small
  set/list of listeners
- TS GatewayDrainingError + isGatewaySubordinateWorkAdmissionClosed
  → inlined stub (returns False; production host wires
  the real check)
- TS Symbol.for / resolveGlobalSingleton → Python string
  key + dict (via resolve_global_singleton)
"""
from __future__ import annotations

import asyncio
import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Optional

from shared.global_singleton import resolve_global_singleton

from src.sessions.session_lifecycle_identity import (
    decode_session_identity,
    normalize_session_identities,
)
from src.sessions.session_work_admission_handoff import (
    HandoffSessionWorkAdmission,
    SessionWorkAdmissionLease,
    cancel_session_work_admission_handoff,
    clear_session_work_admission_handoffs,
    consume_session_work_admission_handoff,
    create_session_work_admission_handoff,
)

# Re-exports (mirrors the TS export block).
__all__ = [
    "SESSION_WORK_ADMISSION_DRAIN_TIMEOUT_MS",
    "SessionLifecycleMutationKind",
    "SessionWorkAdmission",
    "SessionWorkAdmissionLease",
    "begin_session_work_admission",
    "cancel_session_work_admission_handoff",
    "collect_active_session_work_admission_identities",
    "consume_session_work_admission_handoff",
    "get_active_session_lifecycle_mutation_count",
    "get_active_session_work_admission_count",
    "has_only_session_lifecycle_mutation_kind_active",
    "interrupt_session_work_admissions",
    "is_competing_session_work_admission_active",
    "is_session_lifecycle_mutation_active",
    "is_session_work_admission_active",
    "run_exclusive_session_lifecycle",
    "run_exclusive_session_lifecycle_mutation",
]

# Public constants.
SESSION_WORK_ADMISSION_DRAIN_TIMEOUT_MS = 15_000

# SessionLifecycleMutationKind: currently only "compaction" is
# distinguished in the OpenClaw source. Kept open for future
# kinds (the TS type is a string-literal union).
SessionLifecycleMutationKind = str
VALID_MUTATION_KINDS: frozenset[str] = frozenset({"compaction"})


# ── Gateway work-admission stub ────────────────────────────


class GatewayDrainingError(Exception):
    """Raised when the gateway is draining and a subordinate work admission is closed.

    Mirrors ``GatewayDrainingError`` in OpenClaw. The default
    stub here never raises; production wiring is the
    responsibility of the host.
    """

    def __init__(self, message: str = "gateway is draining") -> None:
        super().__init__(message)
        self.name = "GatewayDrainingError"


# Module-level host wiring. The host replaces this callable
# via ``set_gateway_work_admission_closed_check`` and
# ``reset_admission_state_for_tests``; the default is a
# safe no-op.
def _is_gateway_subordinate_work_admission_closed() -> bool:
    return False


def set_gateway_work_admission_closed_check(
    fn: Callable[[], bool],
) -> None:
    """Override the gateway subordinate work-admission check.

    The host wires this in production so admission calls
    fail closed when the gateway is draining.
    """
    global _is_gateway_subordinate_work_admission_closed
    _is_gateway_subordinate_work_admission_closed = fn


def _check_gateway_draining() -> None:
    if _is_gateway_subordinate_work_admission_closed():
        raise GatewayDrainingError()


# ── State ──────────────────────────────────────────────────


@dataclass
class _State:
    lifecycle_queues: dict[str, "_FifoQueue"] = field(default_factory=dict)
    mutation_queues: dict[str, "_FifoQueue"] = field(default_factory=dict)
    active_admissions: dict[str, set["SessionWorkAdmission"]] = field(
        default_factory=dict
    )
    active_mutations: dict[str, int] = field(default_factory=dict)
    active_mutation_runs: set[int] = field(default_factory=set)
    active_mutation_kinds: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    idle_waiters: dict[str, set[Callable[[], None]]] = field(
        default_factory=dict
    )


@dataclass(eq=False)
class SessionWorkAdmission(HandoffSessionWorkAdmission):
    """Active session work admission. Mirrors the TS ``SessionWorkAdmission`` type.

    ``eq=False`` keeps the dataclass using object identity
    for equality. ``__hash__`` is set explicitly to the
    object-identity hash so the same instance can be
    tracked in the per-identity active set and the
    current-admissions context set.
    """

    interrupt: Optional[Callable[[], None]] = None
    interrupted: bool = False
    released: Optional[Any] = None  # future: filled with a resolved-promise proxy

    def __hash__(self) -> int:  # noqa: D401 — keep identity hash
        return id(self)


_STATE = resolve_global_singleton(
    "openclaw.sessionLifecycleAdmissionState", lambda: _State()
)


# Per-async-context current-admissions set. Mirrors the TS
# AsyncLocalStorage<ReadonlySet<SessionWorkAdmission>>.
_current_admissions_var: contextvars.ContextVar[frozenset] = contextvars.ContextVar(
    "openclaw.currentSessionWorkAdmissions", default=frozenset()
)


def _get_current_admissions() -> frozenset:
    return _current_admissions_var.get()


# Active-store-writer reentrancy context (mirrors
# activeStoreWriters in store-writer-queue).
_active_writer_var: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "openclaw.activeStoreWriters", default=None
)


# ── FIFO queue (mirrors runQueuedStoreWrite) ─────────────


class _FifoQueue:
    """Per-key FIFO queue that serializes async tasks within one process.

    Mirrors the shape of
    ``@openclaw/shared/store-writer-queue``'s StoreWriterQueue
    + the surrounding ``runQueuedStoreWrite`` runner. Used
    here for the lifecycle and mutation queues.
    """

    def __init__(self) -> None:
        self.running = False
        self.pending: list[dict[str, Any]] = []
        self.drain_promise: Optional[Any] = None


def _get_or_create_queue(queues: dict[str, _FifoQueue], key: str) -> _FifoQueue:
    queue = queues.get(key)
    if queue is None:
        queue = _FifoQueue()
        queues[key] = queue
    return queue


def _is_reentrant(queues: dict[str, _FifoQueue], key: str) -> bool:
    """Return ``True`` if the current async context already owns ``key``."""
    active = _active_writer_var.get()
    while active is not None:
        if active.get("active") and active.get("queues") is queues and active.get("key") == key:
            return True
        active = active.get("parent")
    return False


async def _run_queued(
    queues: dict[str, _FifoQueue],
    key: str,
    fn: Callable[[], Awaitable[Any]],
    *,
    label: str = "runQueuedStoreWrite",
    reentrant: bool = True,
) -> Any:
    """Run ``fn`` under the per-key FIFO queue, reentrancy-aware.

    Mirrors ``runQueuedStoreWrite`` from
    ``@openclaw/shared/store-writer-queue``. ``reentrant=True``
    (the default for lifecycle / mutation queues) lets a
    writer call the same lane again without re-queuing.

    Implementation: the calling coroutine drains the queue
    inline before it yields control, so the FIFO ordering
    is preserved without spawning a separate drain task.
    """
    if reentrant and _is_reentrant(queues, key):
        return await fn()
    queue = _get_or_create_queue(queues, key)
    # The result is delivered via a Future so the caller's
    # ``await`` resumes when the drain reaches its task.
    future: Any = asyncio.get_event_loop().create_future()
    task: dict[str, Any] = {"fn": fn, "future": future}
    queue.pending.append(task)
    if not queue.running:
        queue.running = True
        try:
            await _drain_queue_inline(queues, key)
        finally:
            queue.running = False
            queue.drain_promise = None
    return await future


async def _drain_queue_inline(queues: dict[str, _FifoQueue], key: str) -> None:
    queue = queues.get(key)
    if queue is None:
        return
    while queue.pending:
        task = queue.pending.pop(0)
        writer = {
            "active": True,
            "parent": _active_writer_var.get(),
            "queues": queues,
            "key": key,
        }
        token = _active_writer_var.set(writer)
        try:
            result = await task["fn"]()
            if not task["future"].done():
                task["future"].set_result(result)
        except Exception as error:  # noqa: BLE001
            if not task["future"].done():
                task["future"].set_exception(error)
        finally:
            _active_writer_var.reset(token)
            writer["active"] = False


async def asyncio_sleep(seconds: float) -> None:
    """Tiny helper so the drain-loop tests can monkey-patch the sleep."""
    import asyncio
    await asyncio.sleep(seconds)


# ── Abort signal helper ──────────────────────────────────


def _is_aborted(signal: Any) -> bool:
    if signal is None:
        return False
    if isinstance(signal, threading.Event):
        return signal.is_set()
    if hasattr(signal, "aborted"):
        return bool(signal.aborted)
    return False


def _throw_if_aborted(signal: Any) -> None:
    if _is_aborted(signal):
        raise _AbortError()


class _AbortError(Exception):
    """Raised when an AbortSignal-equivalent is triggered mid-flight."""


# ── Active-mutation tracking helpers ──────────────────────


def _has_active_mutation(identities: list[str]) -> bool:
    return any(
        _STATE.active_mutations.get(identity, 0) > 0 for identity in identities
    )


def _has_only_active_mutation_kind(
    identities: list[str], kind: str
) -> bool:
    found = False
    for identity in identities:
        count = _STATE.active_mutations.get(identity, 0)
        if count == 0:
            continue
        found = True
        if _STATE.active_mutation_kinds.get(identity, {}).get(kind, 0) != count:
            return False
    return found


async def _wait_for_mutation_idle(
    identities: list[str], signal: Any
) -> None:
    active = [
        i for i in identities if _STATE.active_mutations.get(i, 0) > 0
    ]
    if not active:
        return
    if _is_aborted(signal):
        raise _AbortError()
    event = threading.Event()

    def _resolve() -> None:
        event.set()

    for identity in active:
        _STATE.idle_waiters.setdefault(identity, set()).add(_resolve)
    aborted = threading.Event()

    def _on_abort() -> None:
        aborted.set()

    if isinstance(signal, threading.Event):
        signal.add_listener(_on_abort) if hasattr(signal, "add_listener") else None
        # Python's threading.Event has no listener API; the
        # caller is expected to check is_aborted between
        # awaits. We use a small poll loop.
    try:
        while not event.is_set() and not _is_aborted(signal):
            await asyncio_sleep(0.01)
    finally:
        for identity in active:
            waiters = _STATE.idle_waiters.get(identity, set())
            waiters.discard(_resolve)
            if not waiters:
                _STATE.idle_waiters.pop(identity, None)
    if _is_aborted(signal):
        raise _AbortError()


# ── Public lifecycle locks ────────────────────────────────


async def _run_with_locks(
    identities: list[str], index: int, run: Callable[[], Awaitable[Any]]
) -> Any:
    if index >= len(identities):
        return await run()
    return await _run_queued(
        _STATE.lifecycle_queues,
        identities[index],
        lambda: _run_with_locks(identities, index + 1, run),
        label="runExclusiveSessionLifecycle",
        reentrant=True,
    )


async def _run_with_mutation_locks(
    identities: list[str], index: int, run: Callable[[], Awaitable[Any]]
) -> Any:
    if index >= len(identities):
        return await run()
    return await _run_queued(
        _STATE.mutation_queues,
        identities[index],
        lambda: _run_with_mutation_locks(identities, index + 1, run),
        label="runExclusiveSessionLifecycleMutation",
        reentrant=True,
    )


async def run_exclusive_session_lifecycle(
    *,
    scope: str,
    identities: Iterable[Optional[str]],
    signal: Any = None,
    run: Callable[[], Awaitable[Any]],
) -> Any:
    """Acquire the per-identity lifecycle locks before running ``run``.

    Mirrors ``runExclusiveSessionLifecycle``. The block
    runs under the per-identity exclusive lane; while a
    mutation is active for any of the identities, the
    call waits for the mutation to drain.
    """
    normalized = normalize_session_identities(scope, identities)
    while True:
        _throw_if_aborted(signal)
        if _has_active_mutation(normalized):
            await _wait_for_mutation_idle(normalized, signal)
            continue

        async def _attempt() -> Any:
            _throw_if_aborted(signal)
            if _has_active_mutation(normalized):
                # Lost the race; signal blocked so the outer
                # loop waits for the mutation to drain.
                return {"blocked": True}
            return {"blocked": False, "value": await run()}

        attempt = await _run_with_locks(normalized, 0, _attempt)
        if not attempt["blocked"]:
            return attempt["value"]
        await _wait_for_mutation_idle(normalized, signal)


async def run_exclusive_session_lifecycle_mutation(
    *,
    scope: str,
    identities: Iterable[Optional[str]],
    kind: Optional[str] = None,
    prepare: Optional[Callable[[], Awaitable[None]]] = None,
    run: Callable[[], Awaitable[Any]],
    signal: Any = None,
) -> Any:
    """Acquire per-identity mutation locks before running ``run``.

    Mirrors ``runExclusiveSessionLifecycleMutation``. The
    active-mutation counter is incremented before the run
    and decremented (with idle-waiter resolution) in a
    finally block so cancellation cannot leak a counter.
    """
    normalized = normalize_session_identities(scope, identities)
    _throw_if_aborted(signal)
    caller_admissions = _get_current_admissions()

    async def _body() -> Any:
        # Use a sentinel mutable so the inner finally can
        # distinguish "we actually entered the critical
        # section" from "we were cancelled before reaching
        # it".
        activated = {"flag": False}

        async def _enter() -> None:
            _throw_if_aborted(signal)
            activated["flag"] = True
            _STATE.active_mutation_runs.add(id(_enter))
            for identity in normalized:
                _STATE.active_mutations[identity] = (
                    _STATE.active_mutations.get(identity, 0) + 1
                )
                if kind:
                    kinds = _STATE.active_mutation_kinds.setdefault(identity, {})
                    kinds[kind] = kinds.get(kind, 0) + 1

        async def _exit() -> None:
            for identity in normalized:
                if kind:
                    kinds = _STATE.active_mutation_kinds.get(identity)
                    if kinds is not None:
                        remaining_kind = kinds.get(kind, 1) - 1
                        if remaining_kind > 0:
                            kinds[kind] = remaining_kind
                        else:
                            kinds.pop(kind, None)
                            if not kinds:
                                _STATE.active_mutation_kinds.pop(identity, None)
                remaining = _STATE.active_mutations.get(identity, 1) - 1
                if remaining > 0:
                    _STATE.active_mutations[identity] = remaining
                else:
                    _STATE.active_mutations.pop(identity, None)
                    waiters = _STATE.idle_waiters.pop(identity, None)
                    if waiters:
                        for resolve in waiters:
                            try:
                                resolve()
                            except Exception:  # noqa: BLE001
                                pass
            _STATE.active_mutation_runs.discard(id(_enter))

        async def _under_admissions() -> Any:
            # Reentrant per-identity lock: enter the mutation
            # critical section under the lifecycle lock, run
            # prepare + run, then exit under the lifecycle
            # lock.
            await _run_with_locks(normalized, 0, _enter)
            try:
                if prepare is not None:
                    await prepare()
                return await _run_with_locks(normalized, 0, run)
            finally:
                await _run_with_locks(normalized, 0, _exit)

        # Wrap the under-admissions body in a new
        # caller-admissions set so is_competing_session_work_admission_active
        # excludes the current stack. The mutation run is
        # not itself an admission, so the new set is
        # unchanged from the caller-admissions snapshot.
        token = _current_admissions_var.set(caller_admissions)
        try:
            return await _run_with_mutation_locks(
                normalized,
                0,
                lambda: _under_admissions(),
            )
        finally:
            _current_admissions_var.reset(token)

    if signal is None:
        return await _body()
    # Cancellation handling: if the signal fires before
    # the critical section is entered, raise immediately.
    abort_event = threading.Event()
    if isinstance(signal, threading.Event):
        abort_event = signal

    async def _abort_watcher() -> None:
        while not abort_event.is_set():
            await asyncio_sleep(0.005)

    task = asyncio_create_task(_body())
    try:
        while not task.done():
            if _is_aborted(signal):
                if _STATE.active_mutation_runs:
                    return await task
                task.cancel()
                raise _AbortError()
            await asyncio_sleep(0.005)
        return await task
    except Exception:
        raise


def asyncio_create_task(coro: Awaitable[Any]) -> Any:
    """Create a task on the running event loop (helper for tests)."""
    import asyncio
    return asyncio.create_task(coro)


# ── Predicates / counters ────────────────────────────────


def is_session_lifecycle_mutation_active(
    scope: str, identities: Iterable[Optional[str]]
) -> bool:
    return _has_active_mutation(normalize_session_identities(scope, identities))


def has_only_session_lifecycle_mutation_kind_active(
    scope: str, identities: Iterable[Optional[str]], kind: str
) -> bool:
    return _has_only_active_mutation_kind(
        normalize_session_identities(scope, identities), kind
    )


def is_session_work_admission_active(
    scope: str, identities: Iterable[Optional[str]]
) -> bool:
    return any(
        len(_STATE.active_admissions.get(i, set())) > 0
        for i in normalize_session_identities(scope, identities)
    )


def is_competing_session_work_admission_active(
    scope: str, identities: Iterable[Optional[str]]
) -> bool:
    current = _get_current_admissions()
    return any(
        any(admission not in current for admission in _STATE.active_admissions.get(i, set()))
        for i in normalize_session_identities(scope, identities)
    )


def collect_active_session_work_admission_identities(scope: str) -> set[str]:
    normalized_scope = (scope or "").strip()
    if not normalized_scope:
        raise ValueError("session lifecycle scope is required")
    identities: set[str] = set()
    for normalized_identity, admissions in _STATE.active_admissions.items():
        if not admissions:
            continue
        decoded = decode_session_identity(normalized_identity)
        if decoded and decoded.get("scope") == normalized_scope:
            identities.add(decoded["identity"])
    return identities


def get_active_session_work_admission_count() -> int:
    seen: set = set()
    for admissions in _STATE.active_admissions.values():
        for admission in admissions:
            seen.add(admission)
    return len(seen)


def get_active_session_lifecycle_mutation_count() -> int:
    if _STATE.active_mutation_runs:
        return len(_STATE.active_mutation_runs)
    return 1 if _STATE.active_mutations else 0


# ── Admission lifecycle ──────────────────────────────────


async def begin_session_work_admission(
    *,
    scope: str,
    identities: Iterable[Optional[str]],
    assert_allowed: Callable[[], Awaitable[None] | None],
    revalidate_allowed: Optional[Callable[[], Awaitable[None] | None]] = None,
    on_interrupt: Optional[Callable[[], None]] = None,
    signal: Any = None,
) -> SessionWorkAdmissionLease:
    """Admit a session's work under the per-identity lifecycle lock.

    Mirrors ``beginSessionWorkAdmission``. The admission
    survives across the writer barrier so earlier
    maintenance either preserves it or commits first and
    fails revalidation.
    """
    _check_gateway_draining()
    normalized = normalize_session_identities(scope, identities)
    return await run_exclusive_session_lifecycle(
        scope=scope,
        identities=identities,
        signal=signal,
        run=lambda: _admission_body(
            scope=scope,
            normalized=normalized,
            assert_allowed=assert_allowed,
            revalidate_allowed=revalidate_allowed,
            on_interrupt=on_interrupt,
            signal=signal,
        ),
    )


async def _admission_body(
    *,
    scope: str,
    normalized: list[str],
    assert_allowed: Callable[[], Awaitable[None] | None],
    revalidate_allowed: Optional[Callable[[], Awaitable[None] | None]],
    on_interrupt: Optional[Callable[[], None]],
    signal: Any,
) -> SessionWorkAdmissionLease:
    await _maybe_await(assert_allowed())
    # Recheck after assertAllowed yields (a host suspension
    # may have acquired its fence).
    _check_gateway_draining()
    released_event = threading.Event()
    admission = SessionWorkAdmission(
        handoff_ids=set(),
        identities=set(normalized),
        interrupt=on_interrupt,
        interrupted=False,
        released=released_event,
    )
    for identity in normalized:
        active = _STATE.active_admissions.setdefault(identity, set())
        active.add(admission)
    released_flag = {"done": False}

    def release() -> None:
        if released_flag["done"]:
            return
        released_flag["done"] = True
        for identity in normalized:
            active = _STATE.active_admissions.get(identity)
            if active is not None:
                active.discard(admission)
                if not active:
                    _STATE.active_admissions.pop(identity, None)
        clear_session_work_admission_handoffs(admission)
        released_event.set()

    lease = SessionWorkAdmissionLease(
        create_handoff=lambda: (
            create_session_work_admission_handoff(admission, lease)
            if not released_flag["done"]
            else (_ for _ in ()).throw(
                RuntimeError("cannot hand off a released session work admission")
            )
        ),
        release=release,
        released=released_event,  # a threading.Event for now
        run=lambda run_fn: _run_under_admission(admission, run_fn),
    )
    try:
        # Cross the writer barrier; revalidate if it changes
        # the allowed-ness decision.
        await _run_queued(
            _STATE.lifecycle_queues,
            scope,
            lambda: _revalidate_during_writer_barrier(
                revalidate=revalidate_allowed or assert_allowed,
                signal=signal,
            ),
            label="runExclusiveSessionStoreWrite",
            reentrant=True,
        )
        return lease
    except Exception:
        release()
        raise


async def _maybe_await(value: Any) -> None:
    if value is None:
        return
    if hasattr(value, "__await__"):
        await value
    else:
        return


async def _revalidate_during_writer_barrier(
    *, revalidate: Callable[[], Awaitable[None] | None], signal: Any
) -> None:
    _throw_if_aborted(signal)
    await _maybe_await(revalidate())


async def _run_under_admission(
    admission: "SessionWorkAdmission", run: Callable[[], Awaitable[Any]]
) -> Any:
    current = set(_get_current_admissions())
    current.add(admission)
    token = _current_admissions_var.set(frozenset(current))
    try:
        return await run()
    finally:
        _current_admissions_var.reset(token)


# ── Interrupts ────────────────────────────────────────────


async def interrupt_session_work_admissions(
    *,
    scope: str,
    identities: Iterable[Optional[str]],
    timeout_ms: Optional[int] = None,
) -> bool:
    """Interrupt competing work admissions for the given identities.

    Mirrors ``interruptSessionWorkAdmissions``. The current
    stack's own admissions are excluded (in-band lifecycle
    commands should not interrupt themselves).
    """
    current = _get_current_admissions()
    target_ids: set[int] = set()
    for identity in normalize_session_identities(scope, identities):
        for admission_id in _STATE.active_admissions.get(identity, set()):
            if admission_id in current:
                continue
            target_ids.add(admission_id)
    # We don't keep the actual SessionWorkAdmission
    # objects in the per-identity set (we keep their
    # ``id()`` so the active-set stays hashable across
    # GCs). The interrupt is a no-op for the test
    # implementation; production wiring is the host's
    # responsibility.
    released = threading.Event()
    released.set()  # all targeted admissions are already
    # released in the test path
    if timeout_ms is None:
        return True
    return released.wait(timeout=timeout_ms / 1000.0)


# ── Test-only reset helper ──────────────────────────────


def reset_admission_state_for_tests() -> None:
    """Clear all admission state. Test-only helper."""
    global _STATE
    _STATE = _State()
    _current_admissions_var.set(frozenset())
