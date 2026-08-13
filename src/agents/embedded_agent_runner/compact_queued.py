"""jarvis.agents.embedded_agent_runner.compact_queued — queue compact on the right lane.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact.queued.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`compact_embedded_agent_session` — the queued public entry
  point. Acquires a session/global lane, drives the compaction flow,
  and clears the active run handle on exit.
- :func:`locked_compaction_runtime_failure` — failure result for a
  locked session whose persisted harness is unavailable.
- :func:`create_compaction_aborted_result` — failure result for an
  aborted compaction call.
- :func:`resolve_manual_compaction_active_run_session_id` — return
  the active run session id when one is in flight, blocking manual
  compaction.
- :func:`should_defer_owning_context_engine_budget_compaction` —
  return True when the call should defer to the context engine's
  background maintenance loop.
- :func:`build_context_engine_compaction_session_target` —
  normalize a session target from the compaction params.
- :func:`dispose_context_engine` — safe dispose helper.
- :func:`defer_owning_context_engine_budget_compaction` — run the
  context engine's background maintenance and return a deferred
  result.
- :func:`merge_secondary_native_harness_compaction_details` —
  merge native harness compaction details into the parent details.

Phase 7.2c-2 — focused minimal port.

The OpenClaw source is 1000+ lines and tightly coupled to the
context engine, lane queue, harness selection, and runtime plan
layers. The Python port keeps the public surface and the helper
functions but delegates the heavy :func:`compact_embedded_agent_session`
flow to an installable handler so the host (or tests) can plug in
the real implementation incrementally. The default handler is a
minimal pass-through that resolves an active-run conflict, aborts
on signal, and otherwise returns a stub result; the host replaces
it with the real context-engine + harness-aware flow as the
upstream layers land.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from .compact_types import CompactEmbeddedAgentSessionParams
from .logger import log
from .runs import (
    is_embedded_agent_run_handle_active,
    register_active_embedded_run,
    resolve_active_embedded_run_handle_session_id,
    resolve_active_embedded_run_handle_session_id_by_session_file,
    unregister_active_embedded_run,
)
from .types import EmbeddedAgentCompactResult


#: Reason string for failed background context-engine maintenance.
DEFERRED_CONTEXT_ENGINE_COMPACTION_SCHEDULE_FAILURE_REASON: str = (
    "failed to schedule background context-engine maintenance"
)

#: Reason string for manual compaction blocked by an active run.
MANUAL_COMPACTION_ACTIVE_RUN_REASON: str = (
    "manual compaction unavailable while another embedded run is active"
)

#: Reason string for an aborted compaction.
COMPACTION_ABORTED_REASON: str = "compaction aborted"


def locked_compaction_runtime_failure(
    runtime: Optional[str] = None,
) -> EmbeddedAgentCompactResult:
    """Return the failure result for a locked session with no harness.

    Mirrors :func:`lockedCompactionRuntimeFailure``
    (``compact.queued.ts:103-112``).
    """
    reason = (
        f'Model selection is locked to native agent harness "{runtime}", but native compaction is unavailable.'
        if runtime
        else "Model selection is locked but the persisted agent harness is unavailable."
    )
    return {
        "ok": False,
        "compacted": False,
        "reason": reason,
        "failure": {"reason": "model_selection_locked"},
    }


def create_compaction_aborted_result() -> EmbeddedAgentCompactResult:
    """Return the standard aborted-compaction result.

    Mirrors :func:`createCompactionAbortedResult``
    (``compact.queued.ts:120-126``).
    """
    return {
        "ok": False,
        "compacted": False,
        "reason": COMPACTION_ABORTED_REASON,
    }


def resolve_manual_compaction_active_run_session_id(
    params: CompactEmbeddedAgentSessionParams,
) -> Optional[str]:
    """Return the active run session id blocking manual compaction.

    Mirrors :func:`resolveManualCompactionActiveRunSessionId``
    (``compact.queued.ts:128-136``).
    """
    # Prefer explicit session-key or session-file matches before
    # accepting a raw sessionId. This avoids false-positives when a
    # different active run with the same sessionId exists in the
    # global registry (test isolation can be imperfect across the
    # full suite).
    session_key = params.get("sessionKey")
    if session_key:
        sid = resolve_active_embedded_run_handle_session_id(session_key)
        if sid:
            return sid
    sid = resolve_active_embedded_run_handle_session_id_by_session_file(
        params.get("sessionFile", "")
    )
    if sid:
        return sid
    # Fallback: check direct sessionId registration.
    if is_embedded_agent_run_handle_active(params.get("sessionId", "")):
        return params.get("sessionId")
    return None


def should_defer_owning_context_engine_budget_compaction(
    *,
    compact_params: CompactEmbeddedAgentSessionParams,
    context_engine: Any,
) -> bool:
    """Return True if budget compaction should defer to background maintenance.

    Mirrors :func:`shouldDeferOwningContextEngineBudgetCompaction``
    (``compact.queued.ts:138-153``).
    """
    if isinstance(context_engine, dict):
        info = context_engine.get("info") or {}
        maintain = context_engine.get("maintain")
    else:
        info = getattr(context_engine, "info", None) or {}
        maintain = getattr(context_engine, "maintain", None)
    return (
        compact_params.get("deferOwningContextEngineCompaction") is True
        and compact_params.get("trigger") == "budget"
        and (info.get("ownsCompaction") if isinstance(info, dict) else getattr(info, "ownsCompaction", None)) is True
        and (info.get("turnMaintenanceMode") if isinstance(info, dict) else getattr(info, "turnMaintenanceMode", None)) == "background"
        and callable(maintain)
    )


def build_context_engine_compaction_session_target(
    params: CompactEmbeddedAgentSessionParams,
) -> Dict[str, Any]:
    """Build a normalized session target for context-engine compaction.

    Mirrors :func:`buildContextEngineCompactionSessionTarget``
    (``compact.queued.ts:155-171``).
    """
    session_target = params.get("sessionTarget") or {}
    sqlite_marker = _parse_sqlite_session_file_marker(
        params.get("sessionFile", "")
    )
    agent_id = (
        session_target.get("agentId")
        or params.get("agentId")
        or (sqlite_marker or {}).get("agentId")
    )
    session_key = (
        session_target.get("sessionKey")
        or params.get("sessionKey")
        or params.get("sessionId")
    )
    store_path = session_target.get("storePath") or (
        (sqlite_marker or {}).get("storePath")
    )
    out: Dict[str, Any] = {
        "sessionId": (
            session_target.get("sessionId")
            or (sqlite_marker or {}).get("sessionId")
            or params.get("sessionId")
        ),
    }
    if agent_id:
        out["agentId"] = agent_id
    if session_key:
        out["sessionKey"] = session_key
    if store_path:
        out["storePath"] = store_path
    if session_target.get("threadId") is not None:
        out["threadId"] = session_target["threadId"]
    return out


def _parse_sqlite_session_file_marker(session_file: str) -> Optional[Dict[str, Any]]:
    """Parse a sqlite session file marker.

    Mirrors :func:`parseSqliteSessionFileMarker`` from
    ``config/sessions/sqlite-marker.js``. The focused minimal port
    returns ``None`` because the host installs a real parser through
    :func:`set_sqlite_session_file_marker_parser`.
    """
    return _SQLITE_MARKER_PARSER(session_file) if _SQLITE_MARKER_PARSER else None


_SQLITE_MARKER_PARSER: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None


def set_sqlite_session_file_marker_parser(
    parser: Optional[Callable[[str], Optional[Dict[str, Any]]]],
) -> None:
    """Install a custom sqlite session-file-marker parser."""
    global _SQLITE_MARKER_PARSER
    _SQLITE_MARKER_PARSER = parser


async def dispose_context_engine(context_engine: Any) -> None:
    """Safely dispose a context engine.

    Mirrors :func:`disposeContextEngine``
    (``compact.queued.ts:173-181``).
    """
    dispose = getattr(context_engine, "dispose", None)
    if not dispose:
        return
    try:
        result = dispose()
        if result is not None and hasattr(result, "__await__"):
            await result
    except Exception as err:  # noqa: BLE001 — log and continue
        log.warning("context engine dispose failed: %s", err)


async def defer_owning_context_engine_budget_compaction(
    *,
    compact_params: CompactEmbeddedAgentSessionParams,
    context_engine: Any,
    context_engine_runtime_context: Any,
    context_engine_runtime_settings: Any,
) -> EmbeddedAgentCompactResult:
    """Schedule background maintenance and return a deferred result.

    Mirrors :func:`deferOwningContextEngineBudgetCompaction``
    (``compact.queued.ts:183-240``). The Python port delegates the
    actual maintenance call to an installable hook so the real
    context-engine implementation can land in the host.
    """
    deferred_scheduled = False
    deferred_schedule_failure: Any = None
    session_target = build_context_engine_compaction_session_target(compact_params)
    if _DEFERRED_MAINTENANCE_HOOK is not None:
        try:
            await _DEFERRED_MAINTENANCE_HOOK(
                context_engine=context_engine,
                compact_params=compact_params,
                session_target=session_target,
                runtime_context=context_engine_runtime_context,
                runtime_settings=context_engine_runtime_settings,
            )
            deferred_scheduled = True
        except Exception as err:  # noqa: BLE001 — capture and continue
            deferred_schedule_failure = err
    else:
        # No real maintenance hook installed — try the engine's own
        # maintain() if it has one (focused minimal fallback).
        if isinstance(context_engine, dict):
            maintain = context_engine.get("maintain")
        else:
            maintain = getattr(context_engine, "maintain", None)
        if callable(maintain):
            try:
                result = maintain(
                    session_id=compact_params.get("sessionId"),
                    session_key=compact_params.get("sessionKey"),
                    session_target=session_target,
                    reason="turn",
                    runtime_context=context_engine_runtime_context,
                    runtime_settings=context_engine_runtime_settings,
                )
                if result is not None and hasattr(result, "__await__"):
                    await result
                deferred_scheduled = True
            except Exception as err:  # noqa: BLE001
                deferred_schedule_failure = err
    details: Dict[str, Any] = {}
    if deferred_scheduled:
        details["scheduled"] = True
    else:
        details["scheduled"] = False
    if deferred_schedule_failure is not None:
        details["scheduleFailure"] = str(deferred_schedule_failure)
    return {
        "ok": True,
        "compacted": False,
        "reason": "deferred to background context-engine maintenance",
        "result": {"details": details} if details else None,
    }


#: Async hook for background maintenance. The host installs this so
#: the real context-engine implementation can land in stages.
_DEFERRED_MAINTENANCE_HOOK: Optional[Callable[..., Awaitable[Any]]] = None


def set_deferred_maintenance_hook(
    hook: Optional[Callable[..., Awaitable[Any]]],
) -> None:
    """Install a custom deferred maintenance hook."""
    global _DEFERRED_MAINTENANCE_HOOK
    _DEFERRED_MAINTENANCE_HOOK = hook


def merge_secondary_native_harness_compaction_details(
    *,
    details: Any,
    native_result: Optional[EmbeddedAgentCompactResult],
    details_key: str,
) -> Any:
    """Merge native-harness compaction details into the parent details.

    Mirrors :func:`mergeSecondaryNativeHarnessCompactionDetails``
    (``compact.queued.ts:242-265``).
    """
    if native_result is None:
        return details
    if details and isinstance(details, dict) and not isinstance(details, list):
        merged = dict(details)
        merged[details_key] = native_result
        return merged
    if details is not None:
        return {"contextEngine": details, details_key: native_result}
    return {details_key: native_result}


#: Handler that the host installs to drive the heavy compaction flow.
_QUEUED_COMPACTION_HANDLER: Optional[
    Callable[[CompactEmbeddedAgentSessionParams], Awaitable[EmbeddedAgentCompactResult]]
] = None


def set_queued_compaction_handler(
    handler: Optional[
        Callable[[CompactEmbeddedAgentSessionParams], Awaitable[EmbeddedAgentCompactResult]]
    ],
) -> None:
    """Install the host's queued compaction handler.

    The handler receives the full :class:`CompactEmbeddedAgentSessionParams`
    and is expected to perform the lane-enqueue, engine lookup,
    harness resolution, compaction, and side effects. The Python
    port wraps the handler with the active-run guard, abort-signal
    wiring, and active-run handle teardown so the host handler only
    needs to focus on the actual compaction flow.
    """
    global _QUEUED_COMPACTION_HANDLER
    _QUEUED_COMPACTION_HANDLER = handler


async def _default_queued_compaction_handler(
    params: CompactEmbeddedAgentSessionParams,
) -> EmbeddedAgentCompactResult:
    """Default no-op queued handler.

    The real handler lives in the host; this fallback returns a
    structured "no handler" result so callers that forgot to install
    one still get a typed answer.
    """
    return {
        "ok": False,
        "compacted": False,
        "reason": "no queued compaction handler installed",
        "failure": {"reason": "no_handler"},
    }


async def compact_embedded_agent_session(
    params: CompactEmbeddedAgentSessionParams,
) -> EmbeddedAgentCompactResult:
    """Run the queued compaction flow.

    Mirrors :func:`compactEmbeddedAgentSession``
    (``compact.queued.ts:272-310``).

    For non-manual triggers the call delegates to the installed
    handler directly. For ``"manual"`` triggers it acquires a
    session-id handle, wires the abort signal, and clears the
    handle on exit so the queued manual compaction is properly
    bounded.
    """
    if params.get("trigger") != "manual":
        handler = _QUEUED_COMPACTION_HANDLER or _default_queued_compaction_handler
        return await handler(params)
    if resolve_manual_compaction_active_run_session_id(params):
        return {
            "ok": False,
            "compacted": False,
            "reason": MANUAL_COMPACTION_ACTIVE_RUN_REASON,
            "failure": {"reason": "active_run"},
        }
    # Minimal abort controller — the host replaces this with a real
    # AbortController when the agent runtime is in scope.
    class _Controller:
        def __init__(self) -> None:
            self.aborted = False

        def abort(self, reason: Optional[str] = None) -> None:
            self.aborted = True

    controller = _Controller()
    inner_signal = params.get("abortSignal")
    # Compose the abort signals: any of caller-provided or controller.
    effective_signal: Dict[str, Any] = {
        "aborted": bool(getattr(inner_signal, "aborted", False)) or controller.aborted,
    }
    handle: Dict[str, Any] = {
        "kind": "embedded",
        "isStreaming": lambda: True,
        "isCompacting": lambda: True,
        "abort": controller.abort,
        "cancel": controller.abort,
    }
    register_active_embedded_run(
        session_id=params.get("sessionId", ""),
        handle=handle,
        session_key=params.get("sessionKey"),
        session_file=params.get("sessionFile"),
    )
    try:
        handler = _QUEUED_COMPACTION_HANDLER or _default_queued_compaction_handler
        merged_params: CompactEmbeddedAgentSessionParams = {
            **params,
            "abortSignal": effective_signal,
        }
        return await handler(merged_params)
    finally:
        unregister_active_embedded_run(
            session_id=params.get("sessionId", ""),
            handle=handle,
            session_key=params.get("sessionKey"),
            session_file=params.get("sessionFile"),
        )


__all__ = [
    "COMPACTION_ABORTED_REASON",
    "DEFERRED_CONTEXT_ENGINE_COMPACTION_SCHEDULE_FAILURE_REASON",
    "MANUAL_COMPACTION_ACTIVE_RUN_REASON",
    "build_context_engine_compaction_session_target",
    "compact_embedded_agent_session",
    "create_compaction_aborted_result",
    "defer_owning_context_engine_budget_compaction",
    "dispose_context_engine",
    "locked_compaction_runtime_failure",
    "merge_secondary_native_harness_compaction_details",
    "resolve_manual_compaction_active_run_session_id",
    "set_deferred_maintenance_hook",
    "set_queued_compaction_handler",
    "set_sqlite_session_file_marker_parser",
    "should_defer_owning_context_engine_budget_compaction",
]
