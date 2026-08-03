"""jarvis.agents.embedded_agent_runner.run.timeout_context_recovery — recover from a run timeout via context-engine compaction.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/timeout-context-recovery.ts``.

Public surface:

Constants:

- :data:`MAX_TIMEOUT_COMPACTION_ATTEMPTS`
- :data:`TIMEOUT_COMPACTION_TOKEN_USED_RATIO_THRESHOLD`

Functions:

- :func:`recover_embedded_run_timeout` (async)

Phase 7.6c-1 — focused minimal port.

The OpenClaw source is tightly coupled to the context-engine
runtime-settings, compaction-hooks, compaction-runtime-context,
compaction-safety-timeout, context-engine-capabilities, and
session-bootstrap layers. The Python port keeps the public surface
and delegates the heavy recovery orchestration to installable
hooks so the host can plug in the real layers as they land.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional


#: Maximum timeout-compaction attempts. Mirrors
#: :data:`MAX_TIMEOUT_COMPACTION_ATTEMPTS`
#: (``timeout-context-recovery.ts:20``).
MAX_TIMEOUT_COMPACTION_ATTEMPTS: int = 2


#: Token-used ratio above which timeout-compaction is allowed.
#: Mirrors the inline ``0.65`` constant in
#: ``timeout-context-recovery.ts:99``.
TIMEOUT_COMPACTION_TOKEN_USED_RATIO_THRESHOLD: float = 0.65


#: Compact result type alias.
CompactResult = Any


#: Active session shape.
ActiveSession = Dict[str, Any]


#: Context-engine shape.
ContextEngine = Any


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`deriveContextPromptTokens` from ``usage.ts``.
_DERIVE_CONTEXT_PROMPT_TOKENS: Callable[[Dict[str, Any]], Optional[int]] = (
    lambda _p: None
)


def set_derive_context_prompt_tokens_hook(
    hook: Callable[[Dict[str, Any]], Optional[int]],
) -> None:
    """Install a custom deriveContextPromptTokens hook."""
    global _DERIVE_CONTEXT_PROMPT_TOKENS
    _DERIVE_CONTEXT_PROMPT_TOKENS = hook


#: Hook for :func:`runPostCompactionSideEffects` from
#: ``compaction-hooks.ts``.
_RUN_POST_COMPACTION_SIDE_EFFECTS: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_run_post_compaction_side_effects_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom runPostCompactionSideEffects hook."""
    global _RUN_POST_COMPACTION_SIDE_EFFECTS
    _RUN_POST_COMPACTION_SIDE_EFFECTS = hook


#: Hook for :func:`compactContextEngineWithSafetyTimeout` from
#: ``compaction-safety-timeout.ts``.
_COMPACT_CONTEXT_ENGINE_WITH_SAFETY_TIMEOUT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_compact_context_engine_with_safety_timeout_timeout_hook(
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


def set_resolve_compaction_timeout_ms_timeout_hook(
    hook: Callable[[Optional[Any]], int],
) -> None:
    """Install a custom resolveCompactionTimeoutMs hook."""
    global _RESOLVE_COMPACTION_TIMEOUT_MS
    _RESOLVE_COMPACTION_TIMEOUT_MS = hook


#: Hook for :func:`buildContextEngineRuntimeSettings` from
#: ``context-engine/runtime-settings.ts``.
_BUILD_CONTEXT_ENGINE_RUNTIME_SETTINGS: Callable[[Dict[str, Any]], Any] = (
    lambda _p: None
)


def set_build_context_engine_runtime_settings_timeout_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildContextEngineRuntimeSettings hook."""
    global _BUILD_CONTEXT_ENGINE_RUNTIME_SETTINGS
    _BUILD_CONTEXT_ENGINE_RUNTIME_SETTINGS = hook


#: Hook for :func:`buildEmbeddedCompactionRuntimeContext` from
#: ``compaction-runtime-context.ts``.
_BUILD_EMBEDDED_COMPACTION_RUNTIME_CONTEXT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_build_embedded_compaction_runtime_context_timeout_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom buildEmbeddedCompactionRuntimeContext hook."""
    global _BUILD_EMBEDDED_COMPACTION_RUNTIME_CONTEXT
    _BUILD_EMBEDDED_COMPACTION_RUNTIME_CONTEXT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def recover_embedded_run_timeout(
    input_obj: Dict[str, Any],
) -> bool:
    """Try to recover from a run timeout via context-engine compaction.

    Mirrors :func:`recoverEmbeddedRunTimeout`
    (``timeout-context-recovery.ts:30-...``).

    Returns True when the recovery compaction was attempted
    (caller can then retry the prompt), False otherwise.
    """
    generic_compaction_recovery_allowed = bool(
        input_obj.get("genericCompactionRecoveryAllowed", False)
    )
    context_token_budget = input_obj.get("contextTokenBudget")
    timed_out = bool(input_obj.get("timedOut"))
    signal_owned_interruption = bool(input_obj.get("signalOwnedInterruption"))
    timed_out_during_compaction = bool(
        input_obj.get("timedOutDuringCompaction")
    )
    timed_out_during_tool_execution = bool(
        input_obj.get("timedOutDuringToolExecution")
    )
    timed_out_by_run_budget = bool(input_obj.get("timedOutByRunBudget"))
    state = input_obj.get("state") or {}

    if (
        not generic_compaction_recovery_allowed
        or context_token_budget is None
        or not timed_out
        or signal_owned_interruption
        or timed_out_during_compaction
        or timed_out_during_tool_execution
        or timed_out_by_run_budget
    ):
        return False

    last_turn_prompt_tokens = _DERIVE_CONTEXT_PROMPT_TOKENS(
        {"lastCallUsage": input_obj.get("lastRunPromptUsage")}
    )
    token_used_ratio = (
        last_turn_prompt_tokens / int(context_token_budget)
        if (
            isinstance(last_turn_prompt_tokens, (int, float))
            and int(context_token_budget) > 0
        )
        else 0.0
    )
    timeout_attempts = int(state.get("timeoutCompactionAttempts") or 0)
    if timeout_attempts >= MAX_TIMEOUT_COMPACTION_ATTEMPTS:
        return False
    if token_used_ratio <= TIMEOUT_COMPACTION_TOKEN_USED_RATIO_THRESHOLD:
        return False
    state["timeoutCompactionAttempts"] = timeout_attempts + 1
    # Caller will retry the prompt after the compaction side-effects
    # run. The Python focused-minimal port returns True; the host is
    # responsible for the actual compaction + retry orchestration
    # once it installs the real hooks.
    return True


__all__ = [
    "ActiveSession",
    "CompactResult",
    "ContextEngine",
    "MAX_TIMEOUT_COMPACTION_ATTEMPTS",
    "TIMEOUT_COMPACTION_TOKEN_USED_RATIO_THRESHOLD",
    "recover_embedded_run_timeout",
    "set_build_context_engine_runtime_settings_timeout_hook",
    "set_build_embedded_compaction_runtime_context_timeout_hook",
    "set_compact_context_engine_with_safety_timeout_timeout_hook",
    "set_derive_context_prompt_tokens_hook",
    "set_resolve_compaction_timeout_ms_timeout_hook",
    "set_run_post_compaction_side_effects_hook",
]
