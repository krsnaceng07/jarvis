"""jarvis.agents.embedded_agent_runner.run.terminal_outcome — agent run terminal outcome projection.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/terminal-outcome.ts``.

Public surface:

- :func:`resolve_embedded_run_attempt_terminal_outcome`
- :func:`is_embedded_run_terminal_timeout`
- :func:`is_embedded_run_terminal_abort`
- :func:`is_embedded_run_terminal_interrupted`
- :data:`AGENT_RUN_RESTART_ABORT_STOP_REASON`
- :func:`is_agent_run_restart_abort_reason`
- :func:`resolve_agent_run_abort_lifecycle_fields`

Phase 7.6h-7 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Stop reason used when an internal restart abort owns the prompt race.
AGENT_RUN_RESTART_ABORT_STOP_REASON = "restart_abort"

#: Set of recognized restart-abort reason values.
AGENT_RUN_RESTART_ABORT_REASONS = frozenset(
    {
        "restart_requested",
        "restart_abort",
        "steering_restart",
        "lane_restart",
    }
)


# Installable hooks ---------------------------------------------------------

_resolve_embedded_run_attempt_terminal_outcome_hook = None
_is_embedded_run_terminal_timeout_hook = None
_is_embedded_run_terminal_abort_hook = None
_resolve_agent_run_abort_lifecycle_fields_hook = None


def set_resolve_embedded_run_attempt_terminal_outcome_hook(fn) -> None:
    global _resolve_embedded_run_attempt_terminal_outcome_hook
    _resolve_embedded_run_attempt_terminal_outcome_hook = fn


def set_is_embedded_run_terminal_timeout_hook(fn) -> None:
    global _is_embedded_run_terminal_timeout_hook
    _is_embedded_run_terminal_timeout_hook = fn


def set_is_embedded_run_terminal_abort_hook(fn) -> None:
    global _is_embedded_run_terminal_abort_hook
    _is_embedded_run_terminal_abort_hook = fn


def set_resolve_agent_run_abort_lifecycle_fields_hook(fn) -> None:
    global _resolve_agent_run_abort_lifecycle_fields_hook
    _resolve_agent_run_abort_lifecycle_fields_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def is_agent_run_restart_abort_reason(value: Any) -> bool:
    """Whether ``value`` matches a recognized restart-abort reason.

    Mirrors :func:`isAgentRunRestartAbortReason` (``terminal-outcome.ts``).
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value in AGENT_RUN_RESTART_ABORT_REASONS
    reason = getattr(value, "reason", None) or getattr(value, "stopReason", None)
    if isinstance(reason, str):
        return reason in AGENT_RUN_RESTART_ABORT_REASONS
    return False


def resolve_agent_run_abort_lifecycle_fields(
    abort_signal: Any = None,
) -> Dict[str, Any]:
    """Resolve the abort-driven lifecycle fields from a signal.

    Mirrors :func:`resolveAgentRunAbortLifecycleFields` (``terminal-outcome.ts``).
    """
    if _resolve_agent_run_abort_lifecycle_fields_hook is not None:
        return _resolve_agent_run_abort_lifecycle_fields_hook(abort_signal) or {}
    aborted = False
    stop_reason: Optional[str] = None
    if abort_signal is not None and getattr(abort_signal, "aborted", False):
        aborted = True
        reason = getattr(abort_signal, "reason", None)
        if isinstance(reason, str) and reason:
            stop_reason = "aborted" if reason == "abort" else reason
        else:
            stop_reason = "aborted"
    return {
        "aborted": aborted,
        "stopReason": stop_reason,
    }


def _has_restart_abort_reason(value: Any) -> bool:
    """Walk up to 3 levels of nested ``cause`` looking for a restart reason."""
    candidate = value
    for _ in range(3):
        if is_agent_run_restart_abort_reason(candidate):
            return True
        if not isinstance(candidate, BaseException):
            return False
        try:
            next_candidate = candidate.cause
        except Exception:
            return False
        if next_candidate is None:
            return False
        candidate = next_candidate
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_run_attempt_terminal_outcome(params: Dict[str, Any]) -> Dict[str, Any]:
    """Project private attempt metadata into the canonical agent terminal outcome.

    Mirrors :func:`resolveEmbeddedRunAttemptTerminalOutcome``
    (``terminal-outcome.ts``).
    """
    if _resolve_embedded_run_attempt_terminal_outcome_hook is not None:
        return _resolve_embedded_run_attempt_terminal_outcome_hook(params) or {}
    attempt = params.get("attempt") if isinstance(params.get("attempt"), dict) else {}
    assistant = params.get("assistant") if isinstance(params.get("assistant"), dict) else None
    abort_fields = resolve_agent_run_abort_lifecycle_fields(params.get("abortSignal"))
    attempt_timed_out = bool(attempt.get("timedOut") or attempt.get("idleTimedOut"))
    timed_out = attempt_timed_out or abort_fields.get("stopReason") == "timeout"
    prompt_timeout = attempt.get("promptTimeoutOutcome")
    prompt_timeout = prompt_timeout if isinstance(prompt_timeout, dict) else {}
    timed_out_during_prompt = (
        attempt_timed_out
        and not attempt.get("timedOutDuringCompaction")
        and attempt.get("timedOutDuringToolExecution") is not True
    )
    timeout_phase = prompt_timeout.get("timeoutPhase") or (
        "provider" if timed_out_during_prompt else None
    )
    provider_started = prompt_timeout.get("providerStarted")
    if provider_started is None and timed_out_during_prompt:
        provider_started = True
    restart_aborted = _has_restart_abort_reason(attempt.get("promptError"))
    assistant_stop_reason = (
        None
        if attempt.get("promptError")
        else (assistant.get("stopReason") if isinstance(assistant, dict) else None)
    )
    unattributed_attempt_timeout = (
        attempt_timed_out and timeout_phase is None and provider_started is not True
    )
    if unattributed_attempt_timeout:
        stop_reason = None
    else:
        stop_reason = (
            abort_fields.get("stopReason")
            or (AGENT_RUN_RESTART_ABORT_STOP_REASON if restart_aborted else None)
            or ("aborted" if (not timed_out and attempt.get("aborted")) else None)
            or (assistant_stop_reason if not timed_out else None)
        )
    if timed_out:
        status = "timeout"
    elif (
        abort_fields.get("aborted")
        or attempt.get("aborted")
        or attempt.get("promptError")
        or assistant_stop_reason == "error"
    ):
        status = "error"
    else:
        status = "ok"

    return _build_agent_run_terminal_outcome(
        {
            "status": status,
            "error": attempt.get("promptError") or (assistant.get("errorMessage") if isinstance(assistant, dict) else None),
            "stopReason": stop_reason,
            "livenessState": prompt_timeout.get("livenessState"),
            "timeoutPhase": timeout_phase,
            "providerStarted": provider_started,
        }
    )


def _build_agent_run_terminal_outcome(params: Dict[str, Any]) -> Dict[str, Any]:
    """Stand-in for OpenClaw's :func:`buildAgentRunTerminalOutcome`.

    The full implementation lives in ``agent-run-terminal-outcome.ts``; the
    focused port preserves the public field names so consumers can rely on
    ``status``/``reason``/``error``/``stopReason``/``livenessState``.
    """
    status = params.get("status") or "ok"
    error = params.get("error")
    stop_reason = params.get("stopReason")
    liveness_state = params.get("livenessState")
    timeout_phase = params.get("timeoutPhase")
    provider_started = params.get("providerStarted")
    if status == "timeout":
        reason = "hard_timeout" if timeout_phase in ("context", "preempt") else "timed_out"
    elif status == "error" and stop_reason in ("aborted", "cancelled"):
        reason = stop_reason
    elif error is not None and stop_reason is None:
        reason = "error"
    elif stop_reason:
        reason = stop_reason
    else:
        reason = "ok"
    return {
        "status": status,
        "reason": reason,
        "error": error,
        "stopReason": stop_reason,
        "livenessState": liveness_state,
        "timeoutPhase": timeout_phase,
        "providerStarted": provider_started,
    }


def is_embedded_run_terminal_timeout(outcome: Dict[str, Any]) -> bool:
    """Whether the terminal outcome represents a timeout.

    Mirrors :func:`isEmbeddedRunTerminalTimeout` (``terminal-outcome.ts``).
    """
    if _is_embedded_run_terminal_timeout_hook is not None:
        return bool(_is_embedded_run_terminal_timeout_hook(outcome))
    if not isinstance(outcome, dict):
        return False
    return outcome.get("reason") in ("hard_timeout", "timed_out")


def is_embedded_run_terminal_abort(outcome: Dict[str, Any]) -> bool:
    """Whether the terminal outcome represents an abort.

    Mirrors :func:`isEmbeddedRunTerminalAbort` (``terminal-outcome.ts``).
    """
    if _is_embedded_run_terminal_abort_hook is not None:
        return bool(_is_embedded_run_terminal_abort_hook(outcome))
    if not isinstance(outcome, dict):
        return False
    return outcome.get("reason") in ("aborted", "cancelled")


def is_embedded_run_terminal_interrupted(outcome: Dict[str, Any]) -> bool:
    """Whether the terminal outcome represents an interruption (timeout or abort).

    Mirrors :func:`isEmbeddedRunTerminalInterrupted` (``terminal-outcome.ts``).
    """
    return is_embedded_run_terminal_timeout(outcome) or is_embedded_run_terminal_abort(outcome)


__all__ = [
    "AGENT_RUN_RESTART_ABORT_STOP_REASON",
    "AGENT_RUN_RESTART_ABORT_REASONS",
    "is_agent_run_restart_abort_reason",
    "resolve_agent_run_abort_lifecycle_fields",
    "resolve_embedded_run_attempt_terminal_outcome",
    "is_embedded_run_terminal_timeout",
    "is_embedded_run_terminal_abort",
    "is_embedded_run_terminal_interrupted",
    "set_resolve_embedded_run_attempt_terminal_outcome_hook",
    "set_is_embedded_run_terminal_timeout_hook",
    "set_is_embedded_run_terminal_abort_hook",
    "set_resolve_agent_run_abort_lifecycle_fields_hook",
]
