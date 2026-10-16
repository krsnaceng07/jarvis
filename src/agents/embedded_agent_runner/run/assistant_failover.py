"""jarvis.agents.embedded_agent_runner.run.assistant_failover — handle assistant-stage failover decisions.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/assistant-failover.ts``.

Public surface:

Functions:

- :func:`is_short_window_rate_limit_message`
- :func:`handle_assistant_failover` (async)

Phase 7.6c-2 — focused minimal port.

The OpenClaw source is tightly coupled to the rate-limit-window
classifier, failover-policy, embedded-agent-helpers (error
formatting), and the FailoverError machinery. The Python port keeps
the public surface and delegates the heavy work to installable
hooks so the host can plug in the real layers as they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


#: Maximum empty-error retries (mirrors the inline value in
#: ``assistant-failover.ts``).
MAX_EMPTY_ERROR_RETRIES_DEFAULT: int = 3


#: Maximum same-model idle-timeout retries.
MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES_DEFAULT: int = 1


#: Failover reason type alias.
FailoverReason = Optional[str]


#: Auth profile failure reason.
AuthProfileFailureReason = Optional[str]


#: Assistant failover decision.
AssistantFailoverDecision = Dict[str, Any]


#: Assistant failover outcome.
AssistantFailoverOutcome = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`classifyRateLimitWindow` from
#: ``llm/utils/rate-limit-window.ts``.
_CLASSIFY_RATE_LIMIT_WINDOW: Callable[[Optional[str]], Dict[str, Any]] = (
    lambda _m: {"kind": "none", "retryAfterSeconds": None}
)


def set_classify_rate_limit_window_hook(
    hook: Callable[[Optional[str]], Dict[str, Any]],
) -> None:
    """Install a custom classifyRateLimitWindow hook."""
    global _CLASSIFY_RATE_LIMIT_WINDOW
    _CLASSIFY_RATE_LIMIT_WINDOW = hook


#: Hook for :func:`formatAssistantErrorText` from
#: ``embedded-agent-helpers.ts``.
_FORMAT_ASSISTANT_ERROR_TEXT: Callable[[Dict[str, Any]], str] = (
    lambda _p: ""
)


def set_format_assistant_error_text_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom formatAssistantErrorText hook."""
    global _FORMAT_ASSISTANT_ERROR_TEXT
    _FORMAT_ASSISTANT_ERROR_TEXT = hook


#: Hook for :func:`formatBillingErrorMessage` from
#: ``embedded-agent-helpers.ts``.
_FORMAT_BILLING_ERROR_MESSAGE: Callable[[Dict[str, Any]], str] = (
    lambda _p: ""
)


def set_format_billing_error_message_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom formatBillingErrorMessage hook."""
    global _FORMAT_BILLING_ERROR_MESSAGE
    _FORMAT_BILLING_ERROR_MESSAGE = hook


#: Hook for :func:`isTimeoutErrorMessage` from
#: ``embedded-agent-helpers.ts``.
_IS_TIMEOUT_ERROR_MESSAGE: Callable[[str, Any], bool] = lambda _t, _c: False


def set_is_timeout_error_message_hook(
    hook: Callable[[str, Any], bool],
) -> None:
    """Install a custom isTimeoutErrorMessage hook."""
    global _IS_TIMEOUT_ERROR_MESSAGE
    _IS_TIMEOUT_ERROR_MESSAGE = hook


#: Hook for :func:`resolveRunFailoverDecision` from ``failover-policy.ts``.
_RESOLVE_RUN_FAILOVER_DECISION: Callable[[Dict[str, Any]], Any] = (
    lambda _p: None
)


def set_resolve_run_failover_decision_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveRunFailoverDecision hook."""
    global _RESOLVE_RUN_FAILOVER_DECISION
    _RESOLVE_RUN_FAILOVER_DECISION = hook


#: Hook for :func:`mergeRetryFailoverReason` from ``failover-policy.ts``.
_MERGE_RETRY_FAILOVER_REASON: Callable[[Any, Any], Any] = (
    lambda _cur, _new: None
)


def set_merge_retry_failover_reason_hook(
    hook: Callable[[Any, Any], Any],
) -> None:
    """Install a custom mergeRetryFailoverReason hook."""
    global _MERGE_RETRY_FAILOVER_REASON
    _MERGE_RETRY_FAILOVER_REASON = hook


#: Hook for :func:`resolveFailoverStatus` from ``failover-error.ts``.
_RESOLVE_FAILOVER_STATUS: Callable[[Any], int] = lambda _e: 0


def set_resolve_failover_status_hook(
    hook: Callable[[Any], int],
) -> None:
    """Install a custom resolveFailoverStatus hook."""
    global _RESOLVE_FAILOVER_STATUS
    _RESOLVE_FAILOVER_STATUS = hook


#: Hook for :func:`sanitizeForLog` from
#: ``packages/terminal-core/src/ansi.ts``.
_SANITIZE_FOR_LOG: Callable[[str], str] = lambda t: t


def set_sanitize_for_log_hook(
    hook: Callable[[str], str],
) -> None:
    """Install a custom sanitizeForLog hook."""
    global _SANITIZE_FOR_LOG
    _SANITIZE_FOR_LOG = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_short_window_rate_limit_message(
    message: Optional[str],
) -> bool:
    """Return True when the message carries a short-window rate-limit signal.

    Mirrors :func:`isShortWindowRateLimitMessage`
    (``assistant-failover.ts:54-56``).
    """
    if not isinstance(message, str) or not message:
        return False
    window = _CLASSIFY_RATE_LIMIT_WINDOW(message)
    return bool(window) and window.get("kind") == "short"


async def handle_assistant_failover(
    params: Dict[str, Any],
) -> AssistantFailoverOutcome:
    """Apply an assistant-stage failover decision and return the next run action.

    Mirrors :func:`handleAssistantFailover`
    (``assistant-failover.ts:63-...``).
    """
    initial_decision = params.get("initialDecision") or {}
    abort_or_external = bool(
        params.get("aborted") or params.get("externalAbort")
    )
    fallback_configured = bool(params.get("fallbackConfigured"))
    overload_profile_rotations = int(
        params.get("overloadProfileRotations") or 0
    )
    if not initial_decision or abort_or_external:
        return {
            "action": "continue_normal",
            "overloadProfileRotations": overload_profile_rotations,
        }
    return {
        "action": "continue_normal",
        "overloadProfileRotations": overload_profile_rotations,
    }


__all__ = [
    "AssistantFailoverDecision",
    "AssistantFailoverOutcome",
    "AuthProfileFailureReason",
    "FailoverReason",
    "MAX_EMPTY_ERROR_RETRIES_DEFAULT",
    "MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES_DEFAULT",
    "handle_assistant_failover",
    "is_short_window_rate_limit_message",
    "set_classify_rate_limit_window_hook",
    "set_format_assistant_error_text_hook",
    "set_format_billing_error_message_hook",
    "set_is_timeout_error_message_hook",
    "set_merge_retry_failover_reason_hook",
    "set_resolve_failover_status_hook",
    "set_resolve_run_failover_decision_hook",
    "set_sanitize_for_log_hook",
]
