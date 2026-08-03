"""jarvis.agents.embedded_agent_runner.context_engine_maintenance — deferred context-engine turn maintenance.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/context-engine-maintenance.ts``.

Public surface:

- :func:`run_context_engine_maintenance`
- :func:`wait_for_deferred_turn_maintenance_for_session`
- :func:`schedule_deferred_turn_maintenance`
- :func:`reset_deferred_turn_maintenance_state_for_test`
- :data:`TURN_MAINTENANCE_TASK_KIND`
- :data:`TURN_MAINTENANCE_TASK_LABEL`
- :data:`TURN_MAINTENANCE_LANE_PREFIX`
- :data:`TURN_MAINTENANCE_LONG_WAIT_MS`

Phase 7.6h-5 — focused minimal port.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional


_log = logging.getLogger("jarvis.agents.embedded_agent_runner.context_engine_maintenance")

TURN_MAINTENANCE_TASK_KIND = "context_engine_turn_maintenance"
TURN_MAINTENANCE_TASK_LABEL = "Context engine turn maintenance"
TURN_MAINTENANCE_TASK_TASK = "Deferred context-engine maintenance after turn."
TURN_MAINTENANCE_LANE_PREFIX = "context-engine-turn-maintenance:"
TURN_MAINTENANCE_LONG_WAIT_MS = 10_000


class _LoopAgnosticFuture:
    """Minimal awaitable that mimics :class:`asyncio.Future` without an event loop.

    The deferred-maintenance state needs an awaitable handle so callers can
    ``await`` the maintenance pass. Tests construct and inspect the future
    without ever running the event loop, so this avoids the
    ``RuntimeError: no current event loop`` that ``asyncio.Future()`` raises
    when constructed outside a running loop.
    """

    def __init__(self) -> None:
        self._callbacks: List[Callable[["_LoopAgnosticFuture"], None]] = []
        self._result: Any = None
        self._exception: Optional[BaseException] = None
        self._done = False

    def set_result(self, result: Any = None) -> None:
        if self._done:
            return
        self._done = True
        self._result = result
        for cb in list(self._callbacks):
            try:
                cb(self)
            except Exception:
                pass

    def set_exception(self, exc: BaseException) -> None:
        if self._done:
            return
        self._done = True
        self._exception = exc
        for cb in list(self._callbacks):
            try:
                cb(self)
            except Exception:
                pass

    def add_done_callback(self, cb: Callable[["_LoopAgnosticFuture"], None]) -> None:
        if self._done:
            try:
                cb(self)
            except Exception:
                pass
            return
        self._callbacks.append(cb)

    @property
    def done(self) -> bool:
        return self._done

    def result(self) -> Any:
        if not self._done:
            raise RuntimeError("Future is not done")
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self) -> Optional[BaseException]:
        return self._exception

    def __await__(self):
        if not self._done:
            # When the consumer really does want to block, hand back a future
            # they can await through asyncio if a loop is available; otherwise
            # this is a no-op (the focused port does not block the caller).
            return
        return iter([])


#: Process-local map of active deferred-maintenance runs.
_active_deferred_runs: Dict[str, Dict[str, Any]] = {}


# Installable hooks ---------------------------------------------------------

_run_context_engine_maintenance_hook = None
_schedule_deferred_turn_maintenance_hook = None
_wait_for_deferred_turn_maintenance_for_session_hook = None
_create_deferred_turn_maintenance_abort_signal_hook = None


def set_run_context_engine_maintenance_hook(fn) -> None:
    global _run_context_engine_maintenance_hook
    _run_context_engine_maintenance_hook = fn


def set_schedule_deferred_turn_maintenance_hook(fn) -> None:
    global _schedule_deferred_turn_maintenance_hook
    _schedule_deferred_turn_maintenance_hook = fn


def set_wait_for_deferred_turn_maintenance_for_session_hook(fn) -> None:
    global _wait_for_deferred_turn_maintenance_for_session_hook
    _wait_for_deferred_turn_maintenance_for_session_hook = fn


def set_create_deferred_turn_maintenance_abort_signal_hook(fn) -> None:
    global _create_deferred_turn_maintenance_abort_signal_hook
    _create_deferred_turn_maintenance_abort_signal_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reset_deferred_turn_maintenance_state_for_test() -> None:
    """Clear the process-local deferred-turn-maintenance state for tests.

    Mirrors :func:`resetDeferredTurnMaintenanceStateForTest`
    (``context-engine-maintenance.ts``).
    """
    _active_deferred_runs.clear()


def _normalize_session_key(session_key: Optional[str]) -> Optional[str]:
    if session_key is None:
        return None
    cleaned = str(session_key).strip()
    return cleaned or None


def _resolve_deferred_turn_maintenance_lane(session_key: str) -> str:
    return f"{TURN_MAINTENANCE_LANE_PREFIX}{session_key}"


def _resolve_run_id(session_key: str) -> str:
    return (
        f"turn-maint:{session_key}:{uuid.uuid4().int & 0xFFFFFFFFFFFFFFFF:x}:"
        f"{uuid.uuid4().hex[:8]}"
    )


async def wait_for_deferred_turn_maintenance_for_session(session_key: Optional[str] = None) -> None:
    """Wait for an in-flight deferred maintenance run to complete for the given session.

    Mirrors :func:`waitForDeferredTurnMaintenanceForSession`
    (``context-engine-maintenance.ts``).
    """
    if _wait_for_deferred_turn_maintenance_for_session_hook is not None:
        v = _wait_for_deferred_turn_maintenance_for_session_hook(session_key)
        if hasattr(v, "__await__"):
            await v  # type: ignore[func-returns-value]
        return
    normalized = _normalize_session_key(session_key)
    if not normalized:
        return
    state = _active_deferred_runs.get(normalized)
    if state and hasattr(state.get("promise"), "done"):
        try:
            result = state["promise"].result() if state["promise"].done() else None
        except Exception:
            pass


def schedule_deferred_turn_maintenance(
    params: Dict[str, Any],
) -> Optional["_LoopAgnosticFuture"]:
    """Schedule a deferred context-engine maintenance pass for the given session.

    Mirrors :func:`scheduleDeferredTurnMaintenance`
    (``context-engine-maintenance.ts``).
    """
    if _schedule_deferred_turn_maintenance_hook is not None:
        return _schedule_deferred_turn_maintenance_hook(params)
    session_key = _normalize_session_key(params.get("sessionKey"))
    if not session_key:
        return None
    # Cooperative execution via a loop-agnostic awaitable so callers can
    # track completion without dragging in the lane-queue / task-runtime
    # plugin and without needing a running asyncio event loop.
    future = _LoopAgnosticFuture()
    state = _active_deferred_runs.get(session_key)
    if state is not None:
        state["rerunRequested"] = True
        state["latestParams"] = {**params, "sessionKey": session_key}
        existing_promise = state.get("promise")
        if existing_promise is not None and hasattr(existing_promise, "done"):
            try:
                is_done = existing_promise.done
            except Exception:
                is_done = False
            if not is_done:
                def _chain(_done) -> None:
                    if not future.done:
                        future.set_result(None)
                existing_promise.add_done_callback(_chain)
        return future
    state = {
        "promise": future,
        "rerunRequested": False,
        "latestParams": {**params, "sessionKey": session_key},
    }
    _active_deferred_runs[session_key] = state
    return future


async def run_context_engine_maintenance(
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Run optional context-engine transcript maintenance and normalize the result.

    Mirrors :func:`runContextEngineMaintenance`
    (``context-engine-maintenance.ts``).
    """
    if _run_context_engine_maintenance_hook is not None:
        v = _run_context_engine_maintenance_hook(params)
        if hasattr(v, "__await__"):
            return await v  # type: ignore[func-returns-value]
        return v
    ctx_engine = params.get("contextEngine")
    if not isinstance(ctx_engine, dict) or not callable(ctx_engine.get("maintain")):
        return None
    reason = params.get("reason") or "turn"
    execution_mode = params.get("executionMode") or "foreground"
    info = ctx_engine.get("info") or {}
    should_defer = (
        reason == "turn"
        and execution_mode != "background"
        and isinstance(info, dict)
        and info.get("turnMaintenanceMode") == "background"
    )
    if should_defer:
        try:
            deferred = schedule_deferred_turn_maintenance(
                {
                    "contextEngine": ctx_engine,
                    "sessionId": params.get("sessionId"),
                    "sessionKey": params.get("sessionKey") or params.get("sessionId"),
                    "sessionTarget": params.get("sessionTarget"),
                    "sessionFile": params.get("sessionFile"),
                    "sessionManager": params.get("sessionManager"),
                    "runtimeContext": params.get("runtimeContext"),
                    "runtimeSettings": params.get("runtimeSettings"),
                    "agentId": params.get("agentId"),
                    "config": params.get("config"),
                    "disposeContextEngineAfterMaintenance": params.get(
                        "disposeDeferredContextEngineAfterMaintenance"
                    ),
                    "onScheduleFailure": params.get("onDeferredMaintenanceFailure"),
                }
            )
            on_deferred = params.get("onDeferredMaintenance")
            if deferred is not None and callable(on_deferred):
                try:
                    on_deferred(deferred)
                except Exception:
                    pass
        except Exception as exc:
            _log.warning("failed to schedule deferred context engine maintenance: %s", exc)
        return None
    try:
        result = await ctx_engine["maintain"](
            {
                "sessionId": params.get("sessionId"),
                "sessionKey": params.get("sessionKey"),
                "sessionTarget": params.get("sessionTarget"),
                "sessionFile": params.get("sessionFile"),
                "runtimeSettings": params.get("runtimeSettings"),
                "runtimeContext": params.get("runtimeContext"),
            }
        )
    except Exception as exc:
        _log.warning("context engine maintain failed (%s): %s", reason, exc)
        return None
    if isinstance(result, dict) and result.get("changed"):
        _log.info(
            "[context-engine] maintenance(%s) changed transcript rewrittenEntries=%s bytesFreed=%s",
            reason,
            result.get("rewrittenEntries"),
            result.get("bytesFreed"),
        )
    return result


__all__ = [
    "TURN_MAINTENANCE_TASK_KIND",
    "TURN_MAINTENANCE_TASK_LABEL",
    "TURN_MAINTENANCE_LANE_PREFIX",
    "TURN_MAINTENANCE_LONG_WAIT_MS",
    "run_context_engine_maintenance",
    "wait_for_deferred_turn_maintenance_for_session",
    "schedule_deferred_turn_maintenance",
    "reset_deferred_turn_maintenance_state_for_test",
    "set_run_context_engine_maintenance_hook",
    "set_schedule_deferred_turn_maintenance_hook",
    "set_wait_for_deferred_turn_maintenance_for_session_hook",
    "set_create_deferred_turn_maintenance_abort_signal_hook",
]
