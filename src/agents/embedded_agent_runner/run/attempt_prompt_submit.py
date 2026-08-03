"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_submit — submit the prompt for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-submit.ts``.

Public surface:

- :func:`submit_embedded_attempt_prompt` (async)

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the submit-embedded-attempt-prompt step.
_SUBMIT_EMBEDDED_ATTEMPT_PROMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_submit_embedded_attempt_prompt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom submitEmbeddedAttemptPrompt hook."""
    global _SUBMIT_EMBEDDED_ATTEMPT_PROMPT
    _SUBMIT_EMBEDDED_ATTEMPT_PROMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def submit_embedded_attempt_prompt(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Submit the prompt for an attempt.

    Mirrors :func:`submitEmbeddedAttemptPrompt`
    (``attempt-prompt-submit.ts``).
    """
    result: Any = await _maybe_await(
        _SUBMIT_EMBEDDED_ATTEMPT_PROMPT(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "submitted": bool(result.get("submitted", True)),
        "result": result.get("result"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "set_submit_embedded_attempt_prompt_hook",
    "submit_embedded_attempt_prompt",
]
