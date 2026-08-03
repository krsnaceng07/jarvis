"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_error — handle prompt-stage errors for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-error.ts``.

Public surface:

- :func:`handle_embedded_attempt_prompt_error` (async)

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded attempt prompt-error outcome.
EmbeddedAttemptPromptErrorOutcome = Dict[str, Any]


#: Installable hook for the handle-embedded-attempt-prompt-error step.
_HANDLE_EMBEDDED_ATTEMPT_PROMPT_ERROR: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_handle_embedded_attempt_prompt_error_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom handleEmbeddedAttemptPromptError hook."""
    global _HANDLE_EMBEDDED_ATTEMPT_PROMPT_ERROR
    _HANDLE_EMBEDDED_ATTEMPT_PROMPT_ERROR = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def handle_embedded_attempt_prompt_error(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptErrorOutcome:
    """Handle a prompt-stage error for an attempt.

    Mirrors :func:`handleEmbeddedAttemptPromptError`
    (``attempt-prompt-error.ts``).
    """
    result: Any = await _maybe_await(
        _HANDLE_EMBEDDED_ATTEMPT_PROMPT_ERROR(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "outcome": result.get("outcome", "complete"),
        "result": result.get("result"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptPromptErrorOutcome",
    "handle_embedded_attempt_prompt_error",
    "set_handle_embedded_attempt_prompt_error_hook",
]
