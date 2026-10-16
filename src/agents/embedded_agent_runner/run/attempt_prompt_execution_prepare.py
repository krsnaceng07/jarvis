"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_execution_prepare — prepare the prompt-execution for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-execution-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_prompt_execution` (async)

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded attempt prompt-execution shape.
EmbeddedAttemptPromptExecution = Dict[str, Any]


#: Installable hook for the prepare-prompt-execution step.
_PREPARE_PROMPT_EXECUTION: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)
_DEFAULT_PREPARE_PROMPT_EXECUTION = _PREPARE_PROMPT_EXECUTION


def set_prepare_prompt_execution_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom prepare-embedded-attempt-prompt-execution hook."""
    global _PREPARE_PROMPT_EXECUTION
    _PREPARE_PROMPT_EXECUTION = (
        _DEFAULT_PREPARE_PROMPT_EXECUTION if hook is None else hook
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_prompt_execution(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptExecution:
    """Prepare the prompt-execution for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptPromptExecution`
    (``attempt-prompt-execution-prepare.ts``).
    """
    prepared: Any = await _maybe_await(
        _PREPARE_PROMPT_EXECUTION(dict(input_obj or {}))
    )
    if not isinstance(prepared, dict):
        prepared = {}
    return {
        "ready": bool(prepared.get("ready", True)),
        "execution": prepared.get("execution") or {},
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptPromptExecution",
    "prepare_embedded_attempt_prompt_execution",
    "set_prepare_prompt_execution_hook",
]
