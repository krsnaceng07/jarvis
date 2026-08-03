"""jarvis.agents.embedded_agent_runner.run.attempt_session_boundary — prepare the session boundary for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session-boundary.ts``.

Public surface:

- :func:`prepare_embedded_attempt_session_boundary`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt session-boundary shape.
EmbeddedAttemptSessionBoundary = Dict[str, Any]


#: Installable hook for the prepare-session-boundary step.
_PREPARE_SESSION_BOUNDARY: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_prepare_session_boundary_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepare-session-boundary hook."""
    global _PREPARE_SESSION_BOUNDARY
    _PREPARE_SESSION_BOUNDARY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_session_boundary(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptSessionBoundary:
    """Prepare the session boundary for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSessionBoundary`
    (``attempt-session-boundary.ts``).
    """
    prepared = _PREPARE_SESSION_BOUNDARY(dict(input_obj or {}))
    if not isinstance(prepared, dict):
        prepared = {}
    return {
        "boundaryTimezone": prepared.get("boundaryTimezone"),
        "includeBoundaryTimestamp": bool(
            prepared.get("includeBoundaryTimestamp", False)
        ),
        "orphanRepair": prepared.get("orphanRepair"),
    }


__all__ = [
    "EmbeddedAttemptSessionBoundary",
    "prepare_embedded_attempt_session_boundary",
    "set_prepare_session_boundary_hook",
]
