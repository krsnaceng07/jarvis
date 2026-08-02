"""jarvis.agents.embedded_agent_runner.runs — run registry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/runs.ts``.

Manages active embedded-agent run
handles, queues, aborts, and
waiters.

Public surface (mirrors the OpenClaw
source):

- :data:`EmbeddedAgentQueueMessageOutcome` —
  the outcome of a queue-message
  call.
- :func:`format_embedded_agent_queue_failure_summary` —
  format a failed-outcome summary.
- :func:`mark_active_embedded_run_abandoned` —
  mark an active run as abandoned.
- :func:`is_embedded_run_abandoned` —
  check if a run was abandoned.
- :func:`queue_embedded_agent_message_with_outcome` —
  sync queue-message (fire-and-
  forget after initial eligibility).
- :func:`queue_embedded_agent_message_with_outcome_async` —
  async queue-message (await the
  handle).
- :func:`is_embedded_agent_run_abortable_for_run_id` —
  check if a run is abortable.
- :func:`clear_embedded_agent_run_abortability_for_run_id` —
  clear a run's abortability.
- :func:`retain_embedded_agent_run_abortability_for_run_id` —
  retain a run's abortability past
  the natural end.

Phase 7.1 — focused minimal port.
The full integration with the
auto-reply registry
(``queueReplyRunMessage`` /
``isReplyRunEvidenceStaleBySessionId``)
lands in 7.1+ (when the
``auto-reply`` module is ported).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Awaitable, Callable, Optional, Union

from .run_state import (
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    ACTIVE_EMBEDDED_RUNS,
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS,
    AbandonedEmbeddedRun,
    EmbeddedAgentQueueHandle,
    EmbeddedAgentQueueMessageOptions,
)
from .session_file_key import resolve_embedded_session_file_key


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.runs"
)


# ============================================================================
# Outcome type
# ============================================================================


#: A queue-message outcome. Mirrors
#: :class:`EmbeddedAgentQueueMessageOutcome`
#: (``runs.ts:73-88``).
EmbeddedAgentQueueMessageOutcome = dict


def _create_queue_failure_outcome(
    session_id: str,
    reason: str,
    error_message: Optional[str] = None,
) -> dict:
    """Build a failed-outcome dict.
    Mirrors :func:`createQueueFailureOutcome`
    (``runs.ts:100-112``)."""
    out: dict = {
        "queued": False,
        "sessionId": session_id,
        "reason": reason,
        "gatewayHealth": "live",
    }
    if error_message:
        out["errorMessage"] = error_message
    return out


def format_embedded_agent_queue_failure_summary(
    outcome: dict,
) -> Optional[str]:
    """Format a failed-outcome
    summary. Mirrors
    :func:`formatEmbeddedAgentQueueFailureSummary`
    (``runs.ts:114-122``)."""
    if not isinstance(outcome, dict):
        return None
    if outcome.get("queued"):
        return None
    error_message = outcome.get("errorMessage")
    error_part = (
        f" error={error_message}" if error_message else ""
    )
    return (
        f"queue_message_failed reason={outcome.get('reason')} "
        f"sessionId={outcome.get('sessionId')} "
        f"gatewayHealth={outcome.get('gatewayHealth')}{error_part}"
    )


# ============================================================================
# Abandonment helpers
# ============================================================================


def _set_active_run_session_key(
    session_key: Optional[str],
    session_id: str,
) -> None:
    """Record the session-key →
    session-id mapping for the
    active run. Mirrors
    :func:`setActiveRunSessionKey`
    (``runs.ts:123-129``)."""
    if not session_key:
        return
    normalized = session_key.strip()
    if not normalized:
        return
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY[normalized] = session_id


def _clear_active_run_session_keys(
    session_id: str,
    session_key: Optional[str] = None,
) -> None:
    """Clear the session-key →
    session-id mapping for a
    finished run. Mirrors
    :func:`clearActiveRunSessionKeys`
    (``runs.ts:131-144``)."""
    if session_key:
        normalized = session_key.strip()
        if (
            normalized
            and ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.get(normalized)
            == session_id
        ):
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.pop(
                normalized, None
            )
        return
    # No specific key — drop every
    # mapping pointing at this
    # session id.
    for key in list(
        ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.keys()
    ):
        if (
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.get(key)
            == session_id
        ):
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.pop(key, None)


def _set_active_run_session_file(
    session_file: Optional[str],
    session_id: str,
) -> None:
    """Record the session-file →
    session-id mapping for the
    active run. Mirrors
    :func:`setActiveRunSessionFile`
    (``runs.ts:146-154``)."""
    if not session_file:
        return
    normalized = session_file.strip()
    if not normalized:
        return
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE[
        resolve_embedded_session_file_key(normalized)
    ] = session_id


def _clear_active_run_session_files(
    session_id: str,
    session_file: Optional[str] = None,
) -> None:
    """Clear the session-file →
    session-id mapping for a
    finished run. Mirrors
    :func:`clearActiveRunSessionFiles`
    (``runs.ts:285-298``)."""
    if session_file:
        normalized = session_file.strip()
        if normalized:
            key = resolve_embedded_session_file_key(normalized)
            if (
                ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.get(key)
                == session_id
            ):
                ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.pop(key, None)
        return
    for key in list(
        ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.keys()
    ):
        if (
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.get(key)
            == session_id
        ):
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.pop(key, None)


def _mark_embedded_run_abandoned(
    session_id: str,
    session_key: Optional[str],
    session_file: Optional[str],
    reason: str,
) -> None:
    """Mark a run as abandoned. Mirrors
    :func:`markEmbeddedRunAbandoned`
    (``runs.ts:214-246``)."""
    normalized_id = (session_id or "").strip()
    if not normalized_id:
        return
    _clear_embedded_run_abandonment(
        session_id=normalized_id,
        session_key=session_key,
        session_file=session_file,
    )
    abandoned: AbandonedEmbeddedRun = {
        "sessionId": normalized_id,
        "abandonedAtMs": _now_ms(),
        "reason": reason,
    }
    if session_key and session_key.strip():
        abandoned["sessionKey"] = session_key.strip()
        ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY[
            session_key.strip()
        ] = normalized_id
    if session_file and session_file.strip():
        abandoned["sessionFile"] = session_file.strip()
        ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE[
            resolve_embedded_session_file_key(
                session_file.strip()
            )
        ] = normalized_id
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID[normalized_id] = abandoned


def _clear_embedded_run_abandonment_by_session_id(
    session_id: str,
) -> None:
    """Clear the abandoned record for
    ``session_id``. Mirrors
    :func:`clearEmbeddedRunAbandonmentBySessionId`
    (``runs.ts:156-176``)."""
    if session_id not in ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID:
        return
    abandoned = ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID.pop(
        session_id
    )
    session_key = abandoned.get("sessionKey")
    if (
        session_key
        and ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY.get(
            session_key
        )
        == session_id
    ):
        ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY.pop(
            session_key, None
        )
    session_file = abandoned.get("sessionFile")
    if session_file:
        key = resolve_embedded_session_file_key(session_file)
        if (
            ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE.get(key)
            == session_id
        ):
            ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE.pop(key, None)


def _clear_embedded_run_abandonment(
    session_id: Optional[str] = None,
    session_key: Optional[str] = None,
    session_file: Optional[str] = None,
) -> None:
    """Clear abandonment by any of
    the three keys. Mirrors
    :func:`clearEmbeddedRunAbandonment`
    (``runs.ts:201-212``)."""
    if session_id and session_id.strip():
        _clear_embedded_run_abandonment_by_session_id(
            session_id.strip()
        )
    if session_key and session_key.strip():
        key = session_key.strip()
        session_id_for_key = (
            ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY.get(key)
        )
        if session_id_for_key:
            _clear_embedded_run_abandonment_by_session_id(
                session_id_for_key
            )
    if session_file and session_file.strip():
        key = resolve_embedded_session_file_key(
            session_file.strip()
        )
        session_id_for_file = (
            ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE.get(key)
        )
        if session_id_for_file:
            _clear_embedded_run_abandonment_by_session_id(
                session_id_for_file
            )


def mark_active_embedded_run_abandoned(
    session_id: str,
    handle: EmbeddedAgentQueueHandle,
    session_key: Optional[str] = None,
    session_file: Optional[str] = None,
    reason: str = "timeout",
) -> bool:
    """Mark an active run as
    abandoned. Mirrors
    :func:`markActiveEmbeddedRunAbandoned`
    (``runs.ts:248-261``).

    Returns ``True`` when the
    active run was found and
    marked, ``False`` when the
    handle doesn't match the active
    run (the run already ended).
    """
    normalized_id = (session_id or "").strip()
    if not normalized_id:
        return False
    if ACTIVE_EMBEDDED_RUNS.get(normalized_id) is not handle:
        return False
    _mark_embedded_run_abandoned(
        session_id=normalized_id,
        session_key=session_key,
        session_file=session_file,
        reason=reason,
    )
    return True


def is_embedded_run_abandoned(
    session_id: Optional[str] = None,
    session_key: Optional[str] = None,
    session_file: Optional[str] = None,
) -> bool:
    """Check if a run was abandoned.
    Mirrors
    :func:`isEmbeddedRunAbandoned`
    (``runs.ts:263-283``)."""
    if session_id and session_id.strip():
        if session_id.strip() in (
            ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID
        ):
            return True
    if session_key and session_key.strip():
        if session_key.strip() in (
            ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY
        ):
            return True
    if session_file and session_file.strip():
        key = resolve_embedded_session_file_key(
            session_file.strip()
        )
        if key in ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE:
            return True
    return False


# ============================================================================
# Active run registration
# ============================================================================


def register_active_embedded_run(
    session_id: str,
    handle: EmbeddedAgentQueueHandle,
    session_key: Optional[str] = None,
    session_file: Optional[str] = None,
) -> None:
    """Register an active embedded
    run in the registry. Records the
    session-id, run-id, session-key,
    and session-file mappings.

    Phase 7.1 — focused minimal port
    of the active-run registration
    flow (``runs.ts`` mid-section).
    """
    normalized = (session_id or "").strip()
    if not normalized:
        return
    ACTIVE_EMBEDDED_RUNS[normalized] = handle
    run_id = handle.get("runId") if isinstance(handle, dict) else None
    if run_id and isinstance(run_id, str) and run_id.strip():
        ACTIVE_EMBEDDED_RUNS_BY_RUN_ID[run_id.strip()] = handle
    _set_active_run_session_key(session_key, normalized)
    _set_active_run_session_file(session_file, normalized)


def unregister_active_embedded_run(
    session_id: str,
    handle: EmbeddedAgentQueueHandle,
    session_key: Optional[str] = None,
    session_file: Optional[str] = None,
) -> None:
    """Unregister an active embedded
    run from the registry. Mirrors
    the cleanup flow at the end of
    a run.
    """
    normalized = (session_id or "").strip()
    if not normalized:
        return
    if ACTIVE_EMBEDDED_RUNS.get(normalized) is handle:
        ACTIVE_EMBEDDED_RUNS.pop(normalized, None)
    run_id = handle.get("runId") if isinstance(handle, dict) else None
    if run_id and isinstance(run_id, str) and run_id.strip():
        ACTIVE_EMBEDDED_RUNS_BY_RUN_ID.pop(run_id.strip(), None)
    _clear_active_run_session_keys(normalized, session_key)
    _clear_active_run_session_files(normalized, session_file)
    # Clear the abandoned record
    # (the run is no longer
    # abandoned — it ended normally).
    _clear_embedded_run_abandonment(
        session_id=normalized,
        session_key=session_key,
        session_file=session_file,
    )


# ============================================================================
# Abortability
# ============================================================================


def _is_embedded_queue_handle_message_injectable(
    handle: EmbeddedAgentQueueHandle,
) -> bool:
    """Check if a queue handle is
    currently accepting messages.
    Mirrors
    :func:`isEmbeddedQueueHandleMessageInjectable`
    (``runs.ts:335-347``)."""
    try:
        if isinstance(handle, dict):
            is_stopped = handle.get("isStopped")
            if is_stopped is not None and callable(is_stopped):
                return not is_stopped()
            is_streaming = handle.get("isStreaming")
            if callable(is_streaming):
                return is_streaming()
            return False
        return False
    except Exception:
        _LOG.warning(
            "isEmbeddedQueueHandleMessageInjectable check failed",
            exc_info=True,
        )
        return False


def _is_embedded_run_handle_abortable(
    handle: EmbeddedAgentQueueHandle,
) -> bool:
    """Check if a queue handle is
    abortable. Mirrors
    :func:`isEmbeddedRunHandleAbortable`
    (``runs.ts:349-361``)."""
    try:
        if isinstance(handle, dict):
            is_abortable = handle.get("isAbortable")
            if is_abortable is None:
                return True
            if callable(is_abortable):
                return is_abortable() is not False
            return bool(is_abortable)
        return True
    except Exception:
        _LOG.warning(
            "isEmbeddedRunHandleAbortable check failed",
            exc_info=True,
        )
        return False


def is_embedded_agent_run_abortable_for_run_id(
    run_id: str,
) -> bool:
    """Check if a run is abortable.
    Mirrors
    :func:`isEmbeddedAgentRunAbortableForRunId`
    (``runs.ts:363-370``)."""
    normalized = (run_id or "").strip()
    if not normalized:
        return True
    handle = ACTIVE_EMBEDDED_RUNS_BY_RUN_ID.get(normalized)
    if handle is None:
        return True
    return _is_embedded_run_handle_abortable(handle)


def clear_embedded_agent_run_abortability_for_run_id(
    run_id: str,
) -> None:
    """Clear a run's abortability.
    Mirrors
    :func:`clearEmbeddedAgentRunAbortabilityForRunId`
    (``runs.ts:372-378``)."""
    normalized = (run_id or "").strip()
    if not normalized:
        return
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID.pop(normalized, None)
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS.discard(normalized)


def retain_embedded_agent_run_abortability_for_run_id(
    run_id: str,
) -> None:
    """Retain a run's abortability
    past the natural end. Mirrors
    :func:`retainEmbeddedAgentRunAbortabilityForRunId`
    (``runs.ts:380-385``)."""
    normalized = (run_id or "").strip()
    if not normalized:
        return
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS.add(normalized)


# ============================================================================
# Queue-message helpers
# ============================================================================


def _format_queue_error(err: Any) -> str:
    """Format a queue error. Mirrors
    :func:`formatQueueError`
    (``runs.ts:331-333``)."""
    if isinstance(err, Exception):
        return str(err)
    return str(err)


def _prepare_embedded_agent_queue_message(
    session_id: str,
    text: str,
    options: Optional[EmbeddedAgentQueueMessageOptions] = None,
) -> dict:
    """Prepare a queue-message. Returns
    either ``{"kind": "complete",
    "outcome": ...}`` or ``{"kind":
    "embedded_run", "handle": ...}``.
    Mirrors
    :func:`prepareEmbeddedAgentQueueMessage`
    (``runs.ts:433-490``).

    Phase 7.1 — focused minimal port
    (skips the
    ``queueReplyRunMessage`` /
    ``isReplyRunEvidenceStaleBySessionId``
    integration; the full
    auto-reply registry lands in
    7.1+).
    """
    handle = ACTIVE_EMBEDDED_RUNS.get(session_id)
    if not handle:
        return {
            "kind": "complete",
            "outcome": _create_queue_failure_outcome(
                session_id, "no_active_run"
            ),
        }
    if not _is_embedded_queue_handle_message_injectable(handle):
        return {
            "kind": "complete",
            "outcome": _create_queue_failure_outcome(
                session_id, "not_streaming"
            ),
        }
    return {"kind": "embedded_run", "handle": handle}


def queue_embedded_agent_message_with_outcome(
    session_id: str,
    text: str,
    options: Optional[EmbeddedAgentQueueMessageOptions] = None,
) -> dict:
    """Sync queue-message (fire-
    and-forget after initial
    eligibility). Mirrors
    :func:`queueEmbeddedAgentMessageWithOutcome`
    (``runs.ts:305-329``).

    Phase 7.1 — focused minimal port
    (the auto-reply integration
    falls through when no active
    run is found; the real
    auto-reply integration lands in
    7.1+).
    """
    prepared = _prepare_embedded_agent_queue_message(
        session_id, text, options
    )
    if prepared["kind"] == "complete":
        return prepared["outcome"]
    handle = prepared["handle"]
    queue_message = (
        handle.get("queueMessage")
        if isinstance(handle, dict)
        else None
    )
    if not callable(queue_message):
        return _create_queue_failure_outcome(
            session_id, "runtime_rejected", "no queueMessage"
        )
    return {
        "queued": True,
        "sessionId": session_id,
        "target": "embedded_run",
        "gatewayHealth": "live",
        "enqueuedAtMs": _now_ms(),
    }


async def queue_embedded_agent_message_with_outcome_async(
    session_id: str,
    text: str,
    options: Optional[EmbeddedAgentQueueMessageOptions] = None,
) -> dict:
    """Async queue-message (await
    the handle). Mirrors
    :func:`queueEmbeddedAgentMessageWithOutcomeAsync`
    (``runs.ts:404-431``)."""
    prepared = _prepare_embedded_agent_queue_message(
        session_id, text, options
    )
    if prepared["kind"] == "complete":
        return prepared["outcome"]
    handle = prepared["handle"]
    queue_message = (
        handle.get("queueMessage")
        if isinstance(handle, dict)
        else None
    )
    if not callable(queue_message):
        return _create_queue_failure_outcome(
            session_id, "runtime_rejected", "no queueMessage"
        )
    enqueued_at = _now_ms()
    try:
        result = queue_message(text, options or {"steeringMode": "all"})
        if hasattr(result, "__await__"):
            await result
        return {
            "queued": True,
            "sessionId": session_id,
            "target": "embedded_run",
            "gatewayHealth": "live",
            "enqueuedAtMs": enqueued_at,
        }
    except Exception as err:
        return _create_queue_failure_outcome(
            session_id,
            "runtime_rejected",
            _format_queue_error(err),
        )


# ============================================================================
# Abort a run
# ============================================================================


def abort_active_embedded_run(
    session_id: str,
    reason: str = "restart",
) -> bool:
    """Abort the active run for
    ``session_id``. Returns
    ``True`` when the run was
    aborted, ``False`` when no
    active run was found or the
    handle is not abortable.

    Phase 7.1 — focused minimal port
    of the abort flow.
    """
    handle = ACTIVE_EMBEDDED_RUNS.get(session_id)
    if handle is None:
        return False
    if not _is_embedded_run_handle_abortable(handle):
        return False
    try:
        abort_fn = (
            handle.get("abort")
            if isinstance(handle, dict)
            else None
        )
        if callable(abort_fn):
            abort_fn(reason)
        else:
            cancel_fn = (
                handle.get("cancel")
                if isinstance(handle, dict)
                else None
            )
            if callable(cancel_fn):
                cancel_fn(reason)
        return True
    except Exception:
        _LOG.warning(
            "abort_active_embedded_run failed",
            exc_info=True,
        )
        return False


# ============================================================================
# Helpers
# ============================================================================


def _now_ms() -> int:
    """Return the current epoch ms."""
    import time
    return int(time.time() * 1000)


# ============================================================================
# Active-run handle queries (Phase 7.2c-2 additions)
# ============================================================================


def is_embedded_agent_run_handle_active(session_id: str) -> bool:
    """Return True if an active run is registered for ``session_id``.

    Mirrors :func:`isEmbeddedAgentRunHandleActive`` from OpenClaw
    ``runs.ts``. Focused minimal port: looks up the
    session-id-keyed run registry.
    """
    normalized = (session_id or "").strip()
    if not normalized:
        return False
    return normalized in ACTIVE_EMBEDDED_RUNS


def resolve_active_embedded_run_handle_session_id(
    session_key: str,
) -> Optional[str]:
    """Return the active run's session id for ``session_key``, if any.

    Mirrors :func:`resolveActiveEmbeddedRunHandleSessionId``
    from OpenClaw ``runs.ts``.
    """
    key = (session_key or "").strip()
    if not key:
        return None
    sid = ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.get(key)
    if not sid:
        return None
    return sid if isinstance(sid, str) else None


def resolve_active_embedded_run_handle_session_id_by_session_file(
    session_file: str,
) -> Optional[str]:
    """Return the active run's session id for ``session_file``, if any.

    Mirrors :func:`resolveActiveEmbeddedRunHandleSessionIdBySessionFile``
    from OpenClaw ``runs.ts``.
    """
    resolved = resolve_embedded_session_file_key(session_file or "")
    if not resolved:
        return None
    sid = ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.get(resolved)
    if not sid:
        return None
    return sid if isinstance(sid, str) else None


# Re-export commonly-used types
# (for callers that import from
# ``runs`` directly).
QueueMessageOutcome = EmbeddedAgentQueueMessageOutcome


__all__ = [
    "ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID",
    "ACTIVE_EMBEDDED_RUNS",
    "ACTIVE_EMBEDDED_RUNS_BY_RUN_ID",
    "EmbeddedAgentQueueMessageOutcome",
    "QueueMessageOutcome",
    "abort_active_embedded_run",
    "clear_embedded_agent_run_abortability_for_run_id",
    "format_embedded_agent_queue_failure_summary",
    "is_embedded_agent_run_abortable_for_run_id",
    "is_embedded_agent_run_handle_active",
    "is_embedded_run_abandoned",
    "queue_embedded_agent_message_with_outcome",
    "queue_embedded_agent_message_with_outcome_async",
    "mark_active_embedded_run_abandoned",
    "register_active_embedded_run",
    "resolve_active_embedded_run_handle_session_id",
    "resolve_active_embedded_run_handle_session_id_by_session_file",
    "retain_embedded_agent_run_abortability_for_run_id",
    "unregister_active_embedded_run",
]
