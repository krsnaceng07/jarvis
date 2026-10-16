"""jarvis.agents.embedded_agent_runner.run.attempt_timeout_prepare — prepare the timeout for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-timeout-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_timeout`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt timeout shape.
EmbeddedAttemptTimeout = Dict[str, Any]


#: Installable hook for the prepare-timeout step.
_PREPARE_TIMEOUT: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_prepare_timeout_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepare-timeout hook."""
    global _PREPARE_TIMEOUT
    _PREPARE_TIMEOUT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_timeout(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptTimeout:
    """Prepare the timeout for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptTimeout`
    (``attempt-timeout-prepare.ts``).
    """
    prepared = _PREPARE_TIMEOUT(dict(input_obj or {}))
    if not isinstance(prepared, dict):
        prepared = {}
    return {
        "getRunAbortDeadlineAtMs": prepared.get("getRunAbortDeadlineAtMs"),
        "clearTimers": prepared.get("clearTimers"),
        "removeAbortSignalListener": prepared.get(
            "removeAbortSignalListener"
        ),
    }


__all__ = [
    "EmbeddedAttemptTimeout",
    "prepare_embedded_attempt_timeout",
    "set_prepare_timeout_hook",
]
