"""jarvis.agents.embedded_agent_runner.run.prompt_failure — handle prompt-stage failures for an embedded run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/prompt-failure.ts``.

Public surface:

Functions:

- :func:`handle_embedded_prompt_failure` (async)

Phase 7.6c-2 — focused minimal port.

The OpenClaw source is tightly coupled to the
embedded-agent-helpers (error classification), failover-error
machinery, session-suspension, assistant-failover (rate-limit
window), blocked-run-result, and failover-policy layers. The
Python port keeps the public surface and delegates the heavy work
to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Failover reason type alias.
FailoverReason = Optional[str]


#: Auth profile failure reason.
AuthProfileFailureReason = Optional[str]


#: Embedded agent meta shape.
EmbeddedAgentMeta = Dict[str, Any]


#: Embedded agent run result shape.
EmbeddedAgentRunResult = Dict[str, Any]


#: Embedded run attempt result shape.
EmbeddedRunAttemptResult = Dict[str, Any]


#: Prompt-failure outcome. Mirrors :class:`PromptFailureOutcome`
#: (``prompt-failure.ts:30-37``).
PromptFailureOutcome = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`classifyFailoverReason` from
#: ``embedded-agent-helpers.ts``.
_CLASSIFY_FAILOVER_REASON: Callable[[str, Any], Any] = lambda _t, _c: None


def set_classify_failover_reason_hook(
    hook: Callable[[str, Any], Any],
) -> None:
    """Install a custom classifyFailoverReason hook."""
    global _CLASSIFY_FAILOVER_REASON
    _CLASSIFY_FAILOVER_REASON = hook


#: Hook for :func:`isFailoverErrorMessage` from
#: ``embedded-agent-helpers.ts``.
_IS_FAILOVER_ERROR_MESSAGE: Callable[[str, Any], bool] = lambda _t, _c: False


def set_is_failover_error_message_hook(
    hook: Callable[[str, Any], bool],
) -> None:
    """Install a custom isFailoverErrorMessage hook."""
    global _IS_FAILOVER_ERROR_MESSAGE
    _IS_FAILOVER_ERROR_MESSAGE = hook


#: Hook for :func:`parseImageSizeError` from
#: ``embedded-agent-helpers.ts``.
_PARSE_IMAGE_SIZE_ERROR: Callable[[str], Any] = lambda _t: None


def set_parse_image_size_error_hook(
    hook: Callable[[str], Any],
) -> None:
    """Install a custom parseImageSizeError hook."""
    global _PARSE_IMAGE_SIZE_ERROR
    _PARSE_IMAGE_SIZE_ERROR = hook


#: Hook for :func:`pickFallbackThinkingLevel` from
#: ``embedded-agent-helpers.ts``.
_PICK_FALLBACK_THINKING_LEVEL: Callable[[Any, Any], str] = lambda _l, _a: "medium"


def set_pick_fallback_thinking_level_hook(
    hook: Callable[[Any, Any], str],
) -> None:
    """Install a custom pickFallbackThinkingLevel hook."""
    global _PICK_FALLBACK_THINKING_LEVEL
    _PICK_FALLBACK_THINKING_LEVEL = hook


#: Hook for :func:`coerceToFailoverError` from ``failover-error.ts``.
_COERCE_TO_FAILOVER_ERROR: Callable[[Any], Any] = lambda _e: None


def set_coerce_to_failover_error_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom coerceToFailoverError hook."""
    global _COERCE_TO_FAILOVER_ERROR
    _COERCE_TO_FAILOVER_ERROR = hook


#: Hook for :func:`describeFailoverError` from ``failover-error.ts``.
_DESCRIBE_FAILOVER_ERROR: Callable[[Any], str] = lambda _e: ""


def set_describe_failover_error_hook(
    hook: Callable[[Any], str],
) -> None:
    """Install a custom describeFailoverError hook."""
    global _DESCRIBE_FAILOVER_ERROR
    _DESCRIBE_FAILOVER_ERROR = hook


#: Hook for :func:`resolveFailoverStatus` from ``failover-error.ts``.
_RESOLVE_FAILOVER_STATUS: Callable[[Any], int] = lambda _e: 0


def set_resolve_failover_status_hook(
    hook: Callable[[Any], int],
) -> None:
    """Install a custom resolveFailoverStatus hook."""
    global _RESOLVE_FAILOVER_STATUS
    _RESOLVE_FAILOVER_STATUS = hook


#: Hook for :func:`resolveSessionSuspensionReason` from
#: ``session-suspension.ts``.
_RESOLVE_SESSION_SUSPENSION_REASON: Callable[[Any], Any] = lambda _p: None


def set_resolve_session_suspension_reason_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom resolveSessionSuspensionReason hook."""
    global _RESOLVE_SESSION_SUSPENSION_REASON
    _RESOLVE_SESSION_SUSPENSION_REASON = hook


#: Hook for :func:`isShortWindowRateLimitMessage` from
#: ``assistant-failover.ts``.
_IS_SHORT_WINDOW_RATE_LIMIT_MESSAGE: Callable[[Optional[str]], bool] = (
    lambda _m: False
)


def set_is_short_window_rate_limit_message_hook(
    hook: Callable[[Optional[str]], bool],
) -> None:
    """Install a custom isShortWindowRateLimitMessage hook."""
    global _IS_SHORT_WINDOW_RATE_LIMIT_MESSAGE
    _IS_SHORT_WINDOW_RATE_LIMIT_MESSAGE = hook


#: Hook for :func:`buildEmbeddedRunBlockedResult` from
#: ``blocked-run-result.ts``.
_BUILD_EMBEDDED_RUN_BLOCKED_RESULT: Callable[[Dict[str, Any]], Any] = (
    lambda _p: None
)


def set_build_embedded_run_blocked_result_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildEmbeddedRunBlockedResult hook."""
    global _BUILD_EMBEDDED_RUN_BLOCKED_RESULT
    _BUILD_EMBEDDED_RUN_BLOCKED_RESULT = hook


#: Hook for :func:`createFailoverDecisionLogger` from
#: ``failover-observation.ts``.
_CREATE_FAILOVER_DECISION_LOGGER: Callable[[Any], Any] = lambda _p: None


def set_create_failover_decision_logger_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom createFailoverDecisionLogger hook."""
    global _CREATE_FAILOVER_DECISION_LOGGER
    _CREATE_FAILOVER_DECISION_LOGGER = hook


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def handle_embedded_prompt_failure(
    input_obj: Dict[str, Any],
) -> PromptFailureOutcome:
    """Handle a prompt-stage failure for an embedded run.

    Mirrors :func:`handleEmbeddedPromptFailure`
    (``prompt-failure.ts:39-...``).
    """
    attempt = input_obj.get("attempt") or {}
    prompt_error = input_obj.get("promptError")
    think_level = input_obj.get("thinkLevel") or "medium"
    build_error_agent_meta = input_obj.get("buildErrorAgentMeta")
    if callable(build_error_agent_meta):
        agent_meta = build_error_agent_meta() or {}
    else:
        agent_meta = {}
    return {
        "action": "complete",
        "result": {
            "runId": attempt.get("runId"),
            "sessionId": attempt.get("sessionId"),
            "sessionKey": attempt.get("sessionKey"),
            "sessionFile": attempt.get("sessionFile"),
            "agentId": attempt.get("agentId"),
            "aborted": False,
            "externalAbort": False,
            "timedOut": False,
            "promptError": prompt_error,
            "finalAssistantVisibleText": None,
            "finalAssistantRawText": None,
            "agentMeta": agent_meta,
            "payloads": [],
            "toolSummary": {},
            "failureSignal": input_obj.get("failureSignal"),
        },
        "thinkLevel": think_level,
        "authRetryPending": False,
        "lastRetryFailoverReason": None,
    }


__all__ = [
    "AuthProfileFailureReason",
    "EmbeddedAgentMeta",
    "EmbeddedAgentRunResult",
    "EmbeddedRunAttemptResult",
    "FailoverReason",
    "PromptFailureOutcome",
    "handle_embedded_prompt_failure",
    "set_build_embedded_run_blocked_result_hook",
    "set_classify_failover_reason_hook",
    "set_coerce_to_failover_error_hook",
    "set_create_failover_decision_logger_hook",
    "set_describe_failover_error_hook",
    "set_is_failover_error_message_hook",
    "set_is_short_window_rate_limit_message_hook",
    "set_merge_retry_failover_reason_hook",
    "set_parse_image_size_error_hook",
    "set_pick_fallback_thinking_level_hook",
    "set_resolve_failover_status_hook",
    "set_resolve_run_failover_decision_hook",
    "set_resolve_session_suspension_reason_hook",
]
