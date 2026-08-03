"""jarvis.agents.embedded_agent_runner.run.attempt_recovery — recover a failed embedded run attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-recovery.ts``.

Public surface:

- :func:`recover_embedded_run_attempt` (async)

Phase 7.6d-3 — focused minimal port.

The OpenClaw source is tightly coupled to the overflow-recovery,
timeout-recovery, assistant-failure, prompt-failure, and
auth-controller layers. The Python port keeps the public surface
and delegates the heavy recovery orchestration to installable
hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Recovery outcome.
AttemptRecoveryOutcome = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the recover-embedded-run-overflow step.
_RECOVER_EMBEDDED_RUN_OVERFLOW: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_recover_embedded_run_overflow_attempt_recovery_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom recoverEmbeddedRunOverflow hook."""
    global _RECOVER_EMBEDDED_RUN_OVERFLOW
    _RECOVER_EMBEDDED_RUN_OVERFLOW = hook


#: Hook for the recover-embedded-run-timeout step.
_RECOVER_EMBEDDED_RUN_TIMEOUT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_recover_embedded_run_timeout_attempt_recovery_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom recoverEmbeddedRunTimeout hook."""
    global _RECOVER_EMBEDDED_RUN_TIMEOUT
    _RECOVER_EMBEDDED_RUN_TIMEOUT = hook


#: Hook for the handle-embedded-assistant-failure step.
_HANDLE_EMBEDDED_ASSISTANT_FAILURE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_handle_embedded_assistant_failure_attempt_recovery_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom handleEmbeddedAssistantFailure hook."""
    global _HANDLE_EMBEDDED_ASSISTANT_FAILURE
    _HANDLE_EMBEDDED_ASSISTANT_FAILURE = hook


#: Hook for the handle-embedded-prompt-failure step.
_HANDLE_EMBEDDED_PROMPT_FAILURE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_handle_embedded_prompt_failure_attempt_recovery_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom handleEmbeddedPromptFailure hook."""
    global _HANDLE_EMBEDDED_PROMPT_FAILURE
    _HANDLE_EMBEDDED_PROMPT_FAILURE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def recover_embedded_run_attempt(
    input_obj: Dict[str, Any],
) -> AttemptRecoveryOutcome:
    """Recover a failed embedded run attempt.

    Mirrors :func:`recoverEmbeddedRunAttempt`
    (``attempt-recovery.ts``).
    """
    result = input_obj.get("result") or {}
    attempt = input_obj.get("attempt") or {}
    recovery: Dict[str, Any] = {
        "action": "none",
        "attemptId": attempt.get("runId"),
    }
    if result.get("promptError"):
        prompt_recovery: Any = await _maybe_await(
            _HANDLE_EMBEDDED_PROMPT_FAILURE(
                {"attempt": attempt, "result": result, "input": input_obj}
            )
        )
        if isinstance(prompt_recovery, dict):
            recovery = {**recovery, **prompt_recovery}
    elif result.get("timedOut"):
        timeout_recovery: Any = await _maybe_await(
            _RECOVER_EMBEDDED_RUN_TIMEOUT(
                {"attempt": attempt, "result": result, "input": input_obj}
            )
        )
        if isinstance(timeout_recovery, dict):
            recovery = {**recovery, **timeout_recovery}
    else:
        assistant_recovery: Any = await _maybe_await(
            _HANDLE_EMBEDDED_ASSISTANT_FAILURE(
                {"attempt": attempt, "result": result, "input": input_obj}
            )
        )
        if isinstance(assistant_recovery, dict):
            recovery = {**recovery, **assistant_recovery}
    return recovery


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AttemptRecoveryOutcome",
    "recover_embedded_run_attempt",
    "set_handle_embedded_assistant_failure_attempt_recovery_hook",
    "set_handle_embedded_prompt_failure_attempt_recovery_hook",
    "set_recover_embedded_run_overflow_attempt_recovery_hook",
    "set_recover_embedded_run_timeout_attempt_recovery_hook",
]
