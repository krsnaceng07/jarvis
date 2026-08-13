"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_dispatch — dispatch the prompt for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-dispatch.ts``.

Public surface:

- :func:`dispatch_embedded_attempt_prompt` (async)

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt prompt-dispatch shape.
EmbeddedAttemptPromptDispatch = Dict[str, Any]


#: Installable hook for the dispatch-prompt step.
_DISPATCH_PROMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)
_DEFAULT_DISPATCH_PROMPT = _DISPATCH_PROMPT


def set_dispatch_prompt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom dispatch-prompt hook."""
    global _DISPATCH_PROMPT
    _DISPATCH_PROMPT = _DEFAULT_DISPATCH_PROMPT if hook is None else hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def dispatch_embedded_attempt_prompt(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptDispatch:
    """Dispatch the prompt for an attempt.

    Mirrors :func:`dispatchEmbeddedAttemptPrompt`
    (``attempt-prompt-dispatch.ts``).
    """
    dispatched: Any = await _maybe_await(
        _DISPATCH_PROMPT(dict(input_obj or {}))
    )
    if not isinstance(dispatched, dict):
        dispatched = {}
    return {
        "promptActiveSession": dispatched.get("promptActiveSession"),
        "sessionPromptState": dispatched.get("sessionPromptState"),
        "toolResultPromptProjectionState": dispatched.get(
            "toolResultPromptProjectionState"
        ),
        "trajectoryRecorder": dispatched.get("trajectoryRecorder"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptPromptDispatch",
    "dispatch_embedded_attempt_prompt",
    "set_dispatch_prompt_hook",
]
