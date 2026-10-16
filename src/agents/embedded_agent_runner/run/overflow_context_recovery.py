"""jarvis.agents.embedded_agent_runner.run.overflow_context_recovery — recover from a context-overflow error mid-run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/overflow-context-recovery.ts``.

Public surface:

Constants:

- :data:`MAX_OVERFLOW_COMPACTION_ATTEMPTS`

Functions:

- :func:`recover_embedded_run_overflow` (async)

Phase 7.6c-1 — focused minimal port.

The OpenClaw source is tightly coupled to the context-engine
runtime-settings, compaction-safety-timeout, compaction-runtime-context,
embedded-agent-helpers (overflow detection), tool-result-truncation,
and session-bootstrap layers. The Python port keeps the public
surface and delegates the heavy recovery orchestration to
installable hooks so the host can plug in the real layers as they
land.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional


#: Maximum overflow-compaction retries. Mirrors
#: :data:`MAX_OVERFLOW_COMPACTION_ATTEMPTS`
#: (``overflow-context-recovery.ts:35``).
MAX_OVERFLOW_COMPACTION_ATTEMPTS: int = 3


#: Recovery outcome. Mirrors
#: :class:`EmbeddedRunOverflowRecoveryOutcome`
#: (``overflow-context-recovery.ts:45-53``).
EmbeddedRunOverflowRecoveryOutcome = Dict[str, Any]


#: Context-engine session target.
ContextEngineSessionTarget = Dict[str, Any]


#: Active session shape.
ActiveSession = Dict[str, Any]


#: Context-engine shape.
ContextEngine = Any


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`isLikelyContextOverflowError` from
#: ``embedded-agent-helpers.ts``.
_IS_LIKELY_CONTEXT_OVERFLOW_ERROR: Callable[[str], bool] = lambda _t: False


def set_is_likely_context_overflow_error_hook(
    hook: Callable[[str], bool],
) -> None:
    """Install a custom isLikelyContextOverflowError hook."""
    global _IS_LIKELY_CONTEXT_OVERFLOW_ERROR
    _IS_LIKELY_CONTEXT_OVERFLOW_ERROR = hook


#: Hook for :func:`isCompactionFailureError` from
#: ``embedded-agent-helpers.ts``.
_IS_COMPACTION_FAILURE_ERROR: Callable[[str], bool] = lambda _t: False


def set_is_compaction_failure_error_hook(
    hook: Callable[[str], bool],
) -> None:
    """Install a custom isCompactionFailureError hook."""
    global _IS_COMPACTION_FAILURE_ERROR
    _IS_COMPACTION_FAILURE_ERROR = hook


#: Hook for :func:`extractObservedOverflowTokenCount` from
#: ``embedded-agent-helpers.ts``.
_EXTRACT_OBSERVED_OVERFLOW_TOKEN_COUNT: Callable[[str], Optional[int]] = (
    lambda _t: None
)


def set_extract_observed_overflow_token_count_hook(
    hook: Callable[[str], Optional[int]],
) -> None:
    """Install a custom extractObservedOverflowTokenCount hook."""
    global _EXTRACT_OBSERVED_OVERFLOW_TOKEN_COUNT
    _EXTRACT_OBSERVED_OVERFLOW_TOKEN_COUNT = hook


#: Hook for :func:`buildContextEngineRuntimeSettings` from
#: ``context-engine/runtime-settings.ts``.
_BUILD_CONTEXT_ENGINE_RUNTIME_SETTINGS: Callable[[Dict[str, Any]], Any] = (
    lambda _p: None
)


def set_build_context_engine_runtime_settings_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildContextEngineRuntimeSettings hook."""
    global _BUILD_CONTEXT_ENGINE_RUNTIME_SETTINGS
    _BUILD_CONTEXT_ENGINE_RUNTIME_SETTINGS = hook


#: Hook for :func:`resolveContextEngineCapabilities` from
#: ``context-engine-capabilities.ts``.
_RESOLVE_CONTEXT_ENGINE_CAPABILITIES: Callable[[Any], Any] = lambda _p: None


def set_resolve_context_engine_capabilities_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom resolveContextEngineCapabilities hook."""
    global _RESOLVE_CONTEXT_ENGINE_CAPABILITIES
    _RESOLVE_CONTEXT_ENGINE_CAPABILITIES = hook


#: Hook for :func:`runContextEngineMaintenance` from
#: ``context-engine-maintenance.ts``.
_RUN_CONTEXT_ENGINE_MAINTENANCE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_run_context_engine_maintenance_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom runContextEngineMaintenance hook."""
    global _RUN_CONTEXT_ENGINE_MAINTENANCE
    _RUN_CONTEXT_ENGINE_MAINTENANCE = hook


#: Hook for :func:`compactContextEngineWithSafetyTimeout` from
#: ``compaction-safety-timeout.ts``.
_COMPACT_CONTEXT_ENGINE_WITH_SAFETY_TIMEOUT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_compact_context_engine_with_safety_timeout_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom compactContextEngineWithSafetyTimeout hook."""
    global _COMPACT_CONTEXT_ENGINE_WITH_SAFETY_TIMEOUT
    _COMPACT_CONTEXT_ENGINE_WITH_SAFETY_TIMEOUT = hook


#: Hook for :func:`resolveCompactionTimeoutMs` from
#: ``compaction-safety-timeout.ts``.
_RESOLVE_COMPACTION_TIMEOUT_MS: Callable[[Optional[Any]], int] = (
    lambda _config: 180_000
)


def set_resolve_compaction_timeout_ms_hook(
    hook: Callable[[Optional[Any]], int],
) -> None:
    """Install a custom resolveCompactionTimeoutMs hook."""
    global _RESOLVE_COMPACTION_TIMEOUT_MS
    _RESOLVE_COMPACTION_TIMEOUT_MS = hook


#: Hook for :func:`buildEmbeddedCompactionRuntimeContext` from
#: ``compaction-runtime-context.ts``.
_BUILD_EMBEDDED_COMPACTION_RUNTIME_CONTEXT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_build_embedded_compaction_runtime_context_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom buildEmbeddedCompactionRuntimeContext hook."""
    global _BUILD_EMBEDDED_COMPACTION_RUNTIME_CONTEXT
    _BUILD_EMBEDDED_COMPACTION_RUNTIME_CONTEXT = hook


#: Hook for the createCompactionDiagId helper.
_CREATE_COMPACTION_DIAG_ID: Callable[[], str] = lambda: "diag"


def set_create_compaction_diag_id_hook(
    hook: Callable[[], str],
) -> None:
    """Install a custom createCompactionDiagId hook."""
    global _CREATE_COMPACTION_DIAG_ID
    _CREATE_COMPACTION_DIAG_ID = hook


#: Hook for the isNoRealConversationCompactionNoop step.
_IS_NO_REAL_CONVERSATION_COMPACTION_NOOP: Callable[[Any], bool] = lambda _p: False


def set_is_no_real_conversation_compaction_noop_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom isNoRealConversationCompactionNoop hook."""
    global _IS_NO_REAL_CONVERSATION_COMPACTION_NOOP
    _IS_NO_REAL_CONVERSATION_COMPACTION_NOOP = hook


#: Hook for the resetNoRealConversationTokenSnapshot step.
_RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT: Callable[[Any], None] = lambda _p: None


def set_reset_no_real_conversation_token_snapshot_hook(
    hook: Callable[[Any], None],
) -> None:
    """Install a custom resetNoRealConversationTokenSnapshot hook."""
    global _RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT
    _RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def recover_embedded_run_overflow(
    input_obj: Dict[str, Any],
) -> EmbeddedRunOverflowRecoveryOutcome:
    """Recover from a context-overflow error mid-run.

    Mirrors :func:`recoverEmbeddedRunOverflow`
    (``overflow-context-recovery.ts:55-...``).
    """
    aborted = bool(input_obj.get("aborted"))
    signal_owned_interruption = bool(input_obj.get("signalOwnedInterruption"))
    prompt_error = input_obj.get("promptError")
    assistant_error_text = input_obj.get("assistantErrorText") or ""
    generic_compaction_recovery_allowed = bool(
        input_obj.get("genericCompactionRecoveryAllowed", False)
    )
    context_token_budget = input_obj.get("contextTokenBudget")
    attempt = input_obj.get("attempt") or {}
    state = input_obj.get("state") or {}
    attempt_compaction_count = int(input_obj.get("attemptCompactionCount") or 0)

    context_overflow_error: Optional[Dict[str, str]] = None
    if not aborted and not signal_owned_interruption:
        if prompt_error:
            error_text = str(prompt_error)
            if _IS_LIKELY_CONTEXT_OVERFLOW_ERROR(error_text):
                context_overflow_error = {
                    "text": error_text,
                    "source": "promptError",
                }
        if (
            context_overflow_error is None
            and assistant_error_text
            and _IS_LIKELY_CONTEXT_OVERFLOW_ERROR(assistant_error_text)
        ):
            context_overflow_error = {
                "text": assistant_error_text,
                "source": "assistantError",
            }

    if (
        context_overflow_error is None
        or not generic_compaction_recovery_allowed
        or context_token_budget is None
    ):
        return {"action": "none"}

    error_text = context_overflow_error["text"]
    observed_overflow_tokens = _EXTRACT_OBSERVED_OVERFLOW_TOKEN_COUNT(error_text)
    preflight_recovery = attempt.get("preflightRecovery") or {}
    preflight_estimated = preflight_recovery.get("estimatedPromptTokens")
    if not isinstance(preflight_estimated, (int, float)) or preflight_estimated <= 0:
        preflight_estimated = None
    else:
        preflight_estimated = int(math.ceil(preflight_estimated)) if preflight_estimated is not None else None
    overflow_token_count_for_compaction = (
        observed_overflow_tokens
        if observed_overflow_tokens is not None
        else (
            preflight_estimated
            if preflight_estimated is not None
            else (
                (int(context_token_budget) + 1)
                if int(context_token_budget) > 0
                else None
            )
        )
    )
    is_compaction_failure = _IS_COMPACTION_FAILURE_ERROR(error_text)
    overflow_attempts = int(state.get("overflowCompactionAttempts") or 0)
    if (
        not is_compaction_failure
        and attempt_compaction_count > 0
        and overflow_attempts < MAX_OVERFLOW_COMPACTION_ATTEMPTS
    ):
        state["overflowCompactionAttempts"] = overflow_attempts + 1
        return {"action": "retry"}

    if (
        not is_compaction_failure
        and overflow_attempts < MAX_OVERFLOW_COMPACTION_ATTEMPTS
    ):
        state["overflowCompactionAttempts"] = overflow_attempts + 1
        prepare_current_transcript_retry = input_obj.get("prepareCurrentTranscriptRetry")
        if callable(prepare_current_transcript_retry):
            try:
                prepare_current_transcript_retry()
            except Exception:
                pass
        return {"action": "retry"}

    surface_user_text = (
        "⚠️ Unable to recover from context overflow. The conversation "
        "may be too large to fit in the model's context window. "
        "Consider starting a new session or using a model with a "
        "larger context window."
    )
    if is_compaction_failure:
        return {
            "action": "surface",
            "kind": "compaction_failure",
            "errorText": error_text,
            "userText": surface_user_text,
        }
    return {
        "action": "surface",
        "kind": "context_overflow",
        "errorText": error_text,
        "userText": surface_user_text,
    }


import math


__all__ = [
    "ActiveSession",
    "ContextEngine",
    "ContextEngineSessionTarget",
    "EmbeddedRunOverflowRecoveryOutcome",
    "MAX_OVERFLOW_COMPACTION_ATTEMPTS",
    "recover_embedded_run_overflow",
    "set_build_context_engine_runtime_settings_hook",
    "set_build_embedded_compaction_runtime_context_hook",
    "set_compact_context_engine_with_safety_timeout_hook",
    "set_create_compaction_diag_id_hook",
    "set_extract_observed_overflow_token_count_hook",
    "set_is_compaction_failure_error_hook",
    "set_is_likely_context_overflow_error_hook",
    "set_is_no_real_conversation_compaction_noop_hook",
    "set_reset_no_real_conversation_token_snapshot_hook",
    "set_resolve_compaction_timeout_ms_hook",
    "set_resolve_context_engine_capabilities_hook",
    "set_run_context_engine_maintenance_hook",
]
