"""jarvis.shared.agent_liveness — liveness-state predicates and formatters.

OpenClaw parity: mirrors ``openclaw-main/src/shared/agent-liveness.ts``.
"""
from __future__ import annotations

from typing import Generic, Optional, TypeVar

TStatus = TypeVar("TStatus", bound=str)


def is_blocked_liveness_state(liveness_state: object) -> bool:
    """Return True if ``liveness_state`` is the normalized ``blocked`` marker.

    Mirrors :func:`isBlockedLivenessState` (``shared/agent-liveness.ts``).
    """
    if not isinstance(liveness_state, str):
        return False
    return liveness_state.strip().lower() == "blocked"


def is_abandoned_liveness_state(liveness_state: object) -> bool:
    """Return True if ``liveness_state`` is the normalized ``abandoned`` marker.

    Mirrors :func:`isAbandonedLivenessState` (``shared/agent-liveness.ts``).
    """
    if not isinstance(liveness_state, str):
        return False
    return liveness_state.strip().lower() == "abandoned"


def format_blocked_liveness_error(error: object) -> str:
    """Format a user-facing wait/status message for a blocked run.

    Mirrors :func:`formatBlockedLivenessError` (``shared/agent-liveness.ts``).
    """
    message = error.strip() if isinstance(error, str) else ""
    return message or "Agent run blocked before producing a usable result."


def format_abandoned_liveness_error(error: object) -> str:
    """Format a user-facing wait/status message for an abandoned run.

    Mirrors :func:`formatAbandonedLivenessError` (``shared/agent-liveness.ts``).
    """
    message = error.strip() if isinstance(error, str) else ""
    return message or "Agent run ended before producing a complete result."


def normalize_blocked_liveness_wait_status(params: dict) -> dict:
    """Coerce any blocked liveness state into an ``error`` status.

    Mirrors :func:`normalizeBlockedLivenessWaitStatus`
    (``shared/agent-liveness.ts``).

    Accepts both ``liveness_state`` (snake_case) and ``livenessState``
    (camelCase) keys for caller convenience.
    """
    error_val = params.get("error")
    error = error_val.strip() if isinstance(error_val, str) else None
    liveness = params.get("liveness_state")
    if liveness is None:
        liveness = params.get("livenessState")
    if not is_blocked_liveness_state(liveness):
        return {"status": params.get("status"), "error": error}
    return {
        "status": "error",
        "error": format_blocked_liveness_error(error),
    }


__all__ = [
    "is_blocked_liveness_state",
    "is_abandoned_liveness_state",
    "format_blocked_liveness_error",
    "format_abandoned_liveness_error",
    "normalize_blocked_liveness_wait_status",
]
