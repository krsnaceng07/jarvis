"""jarvis.agents.embedded_agent_runner.run.attempt_finalize — finalize an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-finalize.ts``.

Public surface:

- :func:`finalize_embedded_attempt`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt final-result shape.
EmbeddedAttemptFinal = Dict[str, Any]


#: Installable hook for the finalize-attempt step.
_FINALIZE_ATTEMPT: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_finalize_attempt_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom finalizeEmbeddedAttempt hook."""
    global _FINALIZE_ATTEMPT
    _FINALIZE_ATTEMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def finalize_embedded_attempt(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptFinal:
    """Finalize an attempt.

    Mirrors :func:`finalizeEmbeddedAttempt`
    (``attempt-finalize.ts``).
    """
    finalized = _FINALIZE_ATTEMPT(dict(input_obj or {}))
    if not isinstance(finalized, dict):
        finalized = {}
    attempt = input_obj.get("attempt") or {}
    return {
        "runId": attempt.get("runId"),
        "sessionId": attempt.get("sessionId"),
        "sessionKey": attempt.get("sessionKey"),
        "sessionFile": attempt.get("sessionFile"),
        "agentId": attempt.get("agentId"),
        "aborted": bool(attempt.get("aborted")),
        "timedOut": bool(attempt.get("timedOut")),
        "promptError": attempt.get("promptError"),
        "messagesSnapshot": attempt.get("messagesSnapshot") or [],
        "lastAssistant": attempt.get("lastAssistant"),
        "attemptUsage": attempt.get("attemptUsage"),
        "toolMetas": attempt.get("toolMetas") or [],
        "replayMetadata": attempt.get("replayMetadata"),
        "clientToolCalls": attempt.get("clientToolCalls") or [],
        "extra": finalized,
    }


__all__ = [
    "EmbeddedAttemptFinal",
    "finalize_embedded_attempt",
    "set_finalize_attempt_hook",
]
