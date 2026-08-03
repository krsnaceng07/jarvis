"""jarvis.agents.embedded_agent_runner.run.attempt_session_settle — create the embedded-attempt session-settle tracker.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session-settle.ts``.

Public surface:

- :func:`create_embedded_attempt_session_settle_tracker`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded attempt session-settle tracker.
EmbeddedAttemptSessionSettleTracker = Dict[str, Any]


#: Installable hook for the create-session-settle-tracker step.
_CREATE_EMBEDDED_ATTEMPT_SESSION_SETTLE_TRACKER: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_create_embedded_attempt_session_settle_tracker_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createEmbeddedAttemptSessionSettleTracker hook."""
    global _CREATE_EMBEDDED_ATTEMPT_SESSION_SETTLE_TRACKER
    _CREATE_EMBEDDED_ATTEMPT_SESSION_SETTLE_TRACKER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_embedded_attempt_session_settle_tracker(
    params: Dict[str, Any],
) -> EmbeddedAttemptSessionSettleTracker:
    """Create the session-settle tracker for an attempt.

    Mirrors :func:`createEmbeddedAttemptSessionSettleTracker`
    (``attempt-session-settle.ts``).
    """
    return _CREATE_EMBEDDED_ATTEMPT_SESSION_SETTLE_TRACKER(dict(params or {}))


__all__ = [
    "EmbeddedAttemptSessionSettleTracker",
    "create_embedded_attempt_session_settle_tracker",
    "set_create_embedded_attempt_session_settle_tracker_hook",
]
