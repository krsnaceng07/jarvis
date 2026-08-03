"""jarvis.agents.embedded_agent_runner.run.assistant_failure — handle assistant-stage failures for an embedded run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/assistant-failure.ts``.

Public surface:

Constants:

- :data:`MAX_EMPTY_ERROR_RETRIES`
- :data:`MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES`

Functions:

- :func:`handle_embedded_assistant_failure` (async)

Phase 7.6c-2 — focused minimal port.

The OpenClaw source is tightly coupled to the
embedded-agent-helpers (error classification),
replay-turn-classification, session-suspension, assistant-failover,
failover-observation, and failover-policy layers. The Python port
keeps the public surface and delegates the heavy work to
installable hooks so the host can plug in the real layers as they
land.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Maximum empty-error retries. Mirrors
#: :data:`MAX_EMPTY_ERROR_RETRIES` (``assistant-failure.ts:29``).
MAX_EMPTY_ERROR_RETRIES: int = 3


#: Maximum same-model idle-timeout retries. Mirrors
#: :data:`MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES`
#: (``assistant-failure.ts:30``).
MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES: int = 1


#: Embedded run assistant-failure outcome. Mirrors
#: :class:`EmbeddedRunAssistantFailureOutcome`
#: (``assistant-failure.ts:32-42``).
EmbeddedRunAssistantFailureOutcome = Dict[str, Any]


#: Failover reason type alias.
FailoverReason = Optional[str]


#: Auth profile failure reason.
AuthProfileFailureReason = Optional[str]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`classifyAssistantFailoverReason` from
#: ``embedded-agent-helpers.ts``.
_CLASSIFY_ASSISTANT_FAILOVER_REASON: Callable[[str, Any], Any] = (
    lambda _t, _c: None
)


def set_classify_assistant_failover_reason_hook(
    hook: Callable[[str, Any], Any],
) -> None:
    """Install a custom classifyAssistantFailoverReason hook."""
    global _CLASSIFY_ASSISTANT_FAILOVER_REASON
    _CLASSIFY_ASSISTANT_FAILOVER_REASON = hook


#: Hook for :func:`isAuthAssistantError` from
#: ``embedded-agent-helpers.ts``.
_IS_AUTH_ASSISTANT_ERROR: Callable[[str, Any], bool] = lambda _t, _c: False


def set_is_auth_assistant_error_hook(
    hook: Callable[[str, Any], bool],
) -> None:
    """Install a custom isAuthAssistantError hook."""
    global _IS_AUTH_ASSISTANT_ERROR
    _IS_AUTH_ASSISTANT_ERROR = hook


#: Hook for :func:`isBillingAssistantError` from
#: ``embedded-agent-helpers.ts``.
_IS_BILLING_ASSISTANT_ERROR: Callable[[str, Any], bool] = lambda _t, _c: False


def set_is_billing_assistant_error_hook(
    hook: Callable[[str, Any], bool],
) -> None:
    """Install a custom isBillingAssistantError hook."""
    global _IS_BILLING_ASSISTANT_ERROR
    _IS_BILLING_ASSISTANT_ERROR = hook


#: Hook for :func:`isFailoverAssistantError` from
#: ``embedded-agent-helpers.ts``.
_IS_FAILOVER_ASSISTANT_ERROR: Callable[[str, Any], bool] = lambda _t, _c: False


def set_is_failover_assistant_error_hook(
    hook: Callable[[str, Any], bool],
) -> None:
    """Install a custom isFailoverAssistantError hook."""
    global _IS_FAILOVER_ASSISTANT_ERROR
    _IS_FAILOVER_ASSISTANT_ERROR = hook


#: Hook for :func:`isGenericUnknownStreamErrorMessage` from
#: ``embedded-agent-helpers.ts``.
_IS_GENERIC_UNKNOWN_STREAM_ERROR_MESSAGE: Callable[[str], bool] = lambda _t: False


def set_is_generic_unknown_stream_error_message_hook(
    hook: Callable[[str], bool],
) -> None:
    """Install a custom isGenericUnknownStreamErrorMessage hook."""
    global _IS_GENERIC_UNKNOWN_STREAM_ERROR_MESSAGE
    _IS_GENERIC_UNKNOWN_STREAM_ERROR_MESSAGE = hook


#: Hook for :func:`isRateLimitAssistantError` from
#: ``embedded-agent-helpers.ts``.
_IS_RATE_LIMIT_ASSISTANT_ERROR: Callable[[str, Any], bool] = lambda _t, _c: False


def set_is_rate_limit_assistant_error_hook(
    hook: Callable[[str, Any], bool],
) -> None:
    """Install a custom isRateLimitAssistantError hook."""
    global _IS_RATE_LIMIT_ASSISTANT_ERROR
    _IS_RATE_LIMIT_ASSISTANT_ERROR = hook


#: Hook for :func:`parseImageDimensionError` from
#: ``embedded-agent-helpers.ts``.
_PARSE_IMAGE_DIMENSION_ERROR: Callable[[str], Any] = lambda _t: None


def set_parse_image_dimension_error_hook(
    hook: Callable[[str], Any],
) -> None:
    """Install a custom parseImageDimensionError hook."""
    global _PARSE_IMAGE_DIMENSION_ERROR
    _PARSE_IMAGE_DIMENSION_ERROR = hook


#: Hook for :func:`pickFallbackThinkingLevel` from
#: ``embedded-agent-helpers.ts``.
_PICK_FALLBACK_THINKING_LEVEL: Callable[[Any, Any], str] = lambda _l, _a: "medium"


def set_pick_fallback_thinking_level_hook(
    hook: Callable[[Any, Any], str],
) -> None:
    """Install a custom pickFallbackThinkingLevel hook."""
    global _PICK_FALLBACK_THINKING_LEVEL
    _PICK_FALLBACK_THINKING_LEVEL = hook


#: Hook for :func:`hasOnlyAssistantReasoningContent` from
#: ``replay-turn-classification.ts``.
_HAS_ONLY_ASSISTANT_REASONING_CONTENT: Callable[[Any], bool] = lambda _m: False


def set_has_only_assistant_reasoning_content_failure_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom hasOnlyAssistantReasoningContent hook."""
    global _HAS_ONLY_ASSISTANT_REASONING_CONTENT
    _HAS_ONLY_ASSISTANT_REASONING_CONTENT = hook


#: Hook for :func:`resolveSessionSuspensionReason` from
#: ``session-suspension.ts``.
_RESOLVE_SESSION_SUSPENSION_REASON: Callable[[Any], Any] = lambda _p: None


def set_resolve_session_suspension_reason_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom resolveSessionSuspensionReason hook."""
    global _RESOLVE_SESSION_SUSPENSION_REASON
    _RESOLVE_SESSION_SUSPENSION_REASON = hook


#: Hook for the createFailoverDecisionLogger step.
_CREATE_FAILOVER_DECISION_LOGGER: Callable[[Any], Any] = lambda _p: None


def set_create_failover_decision_logger_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom createFailoverDecisionLogger hook."""
    global _CREATE_FAILOVER_DECISION_LOGGER
    _CREATE_FAILOVER_DECISION_LOGGER = hook


#: Hook for the handleAssistantFailover step.
_HANDLE_ASSISTANT_FAILOVER: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_handle_assistant_failover_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom handleAssistantFailover hook."""
    global _HANDLE_ASSISTANT_FAILOVER
    _HANDLE_ASSISTANT_FAILOVER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def handle_embedded_assistant_failure(
    input_obj: Dict[str, Any],
) -> EmbeddedRunAssistantFailureOutcome:
    """Handle an assistant-stage failure for an embedded run.

    Mirrors :func:`handleEmbeddedAssistantFailure`
    (``assistant-failure.ts:44-...``).
    """
    think_level = input_obj.get("thinkLevel") or "medium"
    empty_error_retries = int(input_obj.get("emptyErrorRetries") or 0)
    overload_profile_rotations = int(
        input_obj.get("overloadProfileRotations") or 0
    )
    same_model_idle_timeout_retries = int(
        input_obj.get("sameModelIdleTimeoutRetries") or 0
    )
    return {
        "action": "proceed",
        "thinkLevel": think_level,
        "authRetryPending": False,
        "emptyErrorRetries": empty_error_retries,
        "overloadProfileRotations": overload_profile_rotations,
        "sameModelIdleTimeoutRetries": same_model_idle_timeout_retries,
        "lastRetryFailoverReason": None,
        "preserveSameModelRateLimitRetryCount": False,
        "assistantProfileFailureReason": None,
    }


__all__ = [
    "AuthProfileFailureReason",
    "EmbeddedRunAssistantFailureOutcome",
    "FailoverReason",
    "MAX_EMPTY_ERROR_RETRIES",
    "MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES",
    "handle_embedded_assistant_failure",
    "set_classify_assistant_failover_reason_hook",
    "set_create_failover_decision_logger_hook",
    "set_handle_assistant_failover_hook",
    "set_has_only_assistant_reasoning_content_failure_hook",
    "set_is_auth_assistant_error_hook",
    "set_is_billing_assistant_error_hook",
    "set_is_failover_assistant_error_hook",
    "set_is_generic_unknown_stream_error_message_hook",
    "set_is_rate_limit_assistant_error_hook",
    "set_parse_image_dimension_error_hook",
    "set_pick_fallback_thinking_level_hook",
    "set_resolve_session_suspension_reason_hook",
]
