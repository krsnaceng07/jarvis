"""jarvis.agents.embedded_agent_runner.run_state — process-local run state.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run-state.ts``.

Shared process-local state for
active and abandoned embedded-agent
runs. The maps are global-singleton
backed so reloads and lazy imports
inside the same gateway process do
not split active-run bookkeeping.

Public surface (mirrors the OpenClaw
source):

- :data:`EmbeddedAgentQueueHandle` —
  the queue handle shape
  (``run-state.ts:23-38``).
- :data:`EmbeddedAgentQueueMessageOptions` —
  alias for the reply-backend queue
  message options
  (``run-state.ts:40``).
- :data:`ActiveEmbeddedRunSnapshot` —
  the snapshot of an active run
  (``run-state.ts:42-46``).
- :data:`EmbeddedRunWaiter` — the
  waiter shape (``run-state.ts:48-51``).
- :data:`AbandonedEmbeddedRun` —
  the abandoned-run record
  (``run-state.ts:53-59``).
- :data:`ACTIVE_EMBEDDED_RUNS` —
  session-id → queue-handle map.
- :data:`ACTIVE_EMBEDDED_RUNS_BY_RUN_ID` —
  run-id → queue-handle map.
- :data:`RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS` —
  set of run-ids that retain
  abortability.
- :data:`ACTIVE_EMBEDDED_RUN_SNAPSHOTS` —
  session-id → snapshot map.
- :data:`ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY` —
  session-key → session-id map.
- :data:`ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE` —
  session-file → session-id map.
- :data:`ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID` —
  session-id → abandoned-run map.
- :data:`ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY` —
  session-key → session-id map.
- :data:`ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE` —
  session-file → session-id map.
- :data:`EMBEDDED_RUN_WAITERS` —
  session-id → waiter-set map.
- :func:`get_active_embedded_run_count` —
  count active runs.
- :func:`list_active_embedded_run_session_keys` —
  list active session keys.
- :func:`list_active_embedded_run_session_ids` —
  list active session ids.
- :func:`resolve_active_embedded_run_session_id` —
  resolve the current session id.

Phase 7.0 — process-local run
state for Layer 3.
"""
from __future__ import annotations

import threading
from typing import Any, Optional, TypedDict


#: A queue-handle shape. Mirrors
#: :class:`EmbeddedAgentQueueHandle`
#: (``run-state.ts:23-38``).
class EmbeddedAgentQueueHandle(TypedDict, total=False):
    kind: Optional[str]  # "embedded"
    runId: Optional[str]
    queueMessage: Any  # Callable
    isStreaming: Any  # Callable
    isStopped: Any  # Callable
    isAbortable: Any  # Callable
    isCompacting: Any  # Callable
    supportsTranscriptCommitWait: Optional[bool]
    supportsQueueMessageImages: Optional[bool]
    cancel: Any  # Callable
    abort: Any  # Callable
    sourceReplyDeliveryMode: Optional[str]
    taskSuggestionDeliveryMode: Optional[str]


#: A queue-message-options shape.
#: Mirrors the OpenClaw source's
#: ``EmbeddedAgentQueueMessageOptions``
#: type alias (``run-state.ts:40``).
EmbeddedAgentQueueMessageOptions = dict


#: An active-run snapshot. Mirrors
#: :class:`ActiveEmbeddedRunSnapshot`
#: (``run-state.ts:42-46``).
class ActiveEmbeddedRunSnapshot(TypedDict, total=False):
    transcriptLeafId: Optional[str]
    messages: Optional[list]
    inFlightPrompt: Optional[str]


#: A waiter shape. Mirrors
#: :class:`EmbeddedRunWaiter`
#: (``run-state.ts:48-51``).
class EmbeddedRunWaiter(TypedDict, total=False):
    resolve: Any  # Callable
    timer: Optional[Any]  # Timer handle


#: An abandoned-run record. Mirrors
#: :class:`AbandonedEmbeddedRun`
#: (``run-state.ts:53-59``).
class AbandonedEmbeddedRun(TypedDict, total=False):
    sessionId: str
    sessionKey: Optional[str]
    sessionFile: Optional[str]
    abandonedAtMs: int
    reason: str  # "timeout"


# ============================================================================
# Process-local state
# ============================================================================


#: The OpenClaw source uses a
#: ``Symbol.for("openclaw.embeddedRunState")``
#: to look up the singleton. The
#: Python port uses a module-level
#: dict (with a lock) for the same
#: purpose (the singleton is
#: process-local).
_EMBEDDED_RUN_STATE: dict = {
    "activeRuns": {},
    "activeRunsByRunId": {},
    "retainedAbortabilityRunIds": set(),
    "snapshots": {},
    "sessionIdsByKey": {},
    "sessionIdsByFile": {},
    "abandonedRunsBySessionId": {},
    "abandonedRunSessionIdsByKey": {},
    "abandonedRunSessionIdsByFile": {},
    "waiters": {},
}
_STATE_LOCK = threading.Lock()


def _state() -> dict:
    return _EMBEDDED_RUN_STATE


#: session-id → queue-handle map.
#: Mirrors :data:`ACTIVE_EMBEDDED_RUNS`
#: (``run-state.ts:76-78``).
ACTIVE_EMBEDDED_RUNS: dict = _state()["activeRuns"]


#: run-id → queue-handle map. Mirrors
#: :data:`ACTIVE_EMBEDDED_RUNS_BY_RUN_ID`
#: (``run-state.ts:79-81``).
ACTIVE_EMBEDDED_RUNS_BY_RUN_ID: dict = _state()["activeRunsByRunId"]


#: Set of run-ids that retain
#: abortability. Mirrors
#: :data:`RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS`
#: (``run-state.ts:82-84``).
RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS: set = (
    _state()["retainedAbortabilityRunIds"]
)


#: session-id → snapshot map.
ACTIVE_EMBEDDED_RUN_SNAPSHOTS: dict = _state()["snapshots"]


#: session-key → session-id map.
ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY: dict = (
    _state()["sessionIdsByKey"]
)


#: session-file → session-id map.
ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE: dict = (
    _state()["sessionIdsByFile"]
)


#: session-id → abandoned-run map.
ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID: dict = (
    _state()["abandonedRunsBySessionId"]
)


#: session-key → session-id map.
ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY: dict = (
    _state()["abandonedRunSessionIdsByKey"]
)


#: session-file → session-id map.
ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE: dict = (
    _state()["abandonedRunSessionIdsByFile"]
)


#: session-id → waiter-set map.
EMBEDDED_RUN_WAITERS: dict = _state()["waiters"]


# ============================================================================
# Getters
# ============================================================================


def get_active_embedded_run_count() -> int:
    """Count active embedded runs.
    Mirrors :func:`getActiveEmbeddedRunCount`
    (``run-state.ts:108-116``).

    Phase 7.0 — focused minimal port:
    counts only the embedded map
    (the auto-reply registry
    integration lands in 7.1+).
    """
    with _STATE_LOCK:
        return len(ACTIVE_EMBEDDED_RUNS)


def list_active_embedded_run_session_keys() -> list[str]:
    """List active embedded-run
    session keys. Mirrors
    :func:`listActiveEmbeddedRunSessionKeys`
    (``run-state.ts:119-126``)."""
    with _STATE_LOCK:
        keys = list(ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.keys())
    keys.sort()
    return keys


def list_active_embedded_run_session_ids() -> list[str]:
    """List active embedded-run
    session ids. Mirrors
    :func:`listActiveEmbeddedRunSessionIds`
    (``run-state.ts:129-138``)."""
    with _STATE_LOCK:
        ids = set(ACTIVE_EMBEDDED_RUNS.keys())
        ids.update(ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.values())
        ids.update(ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.values())
    return sorted(ids)


def resolve_active_embedded_run_session_id(
    session_key: str,
) -> Optional[str]:
    """Resolve the current session id
    for an active run. Mirrors
    :func:`resolveActiveEmbeddedRunSessionId`
    (``run-state.ts:141-150``)."""
    normalized = session_key.strip() if session_key else ""
    if not normalized:
        return None
    with _STATE_LOCK:
        return ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.get(normalized)


__all__ = [
    "ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID",
    "ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE",
    "ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY",
    "ACTIVE_EMBEDDED_RUNS",
    "ACTIVE_EMBEDDED_RUNS_BY_RUN_ID",
    "ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE",
    "ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY",
    "ACTIVE_EMBEDDED_RUN_SNAPSHOTS",
    "AbandonedEmbeddedRun",
    "ActiveEmbeddedRunSnapshot",
    "EMBEDDED_RUN_WAITERS",
    "EmbeddedAgentQueueHandle",
    "EmbeddedAgentQueueMessageOptions",
    "EmbeddedRunWaiter",
    "RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS",
    "get_active_embedded_run_count",
    "list_active_embedded_run_session_ids",
    "list_active_embedded_run_session_keys",
    "resolve_active_embedded_run_session_id",
]
