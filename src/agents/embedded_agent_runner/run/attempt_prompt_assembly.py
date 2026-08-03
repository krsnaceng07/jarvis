"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_assembly — assemble the prompt for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-assembly.ts``.

Public surface:

- :func:`prepare_embedded_attempt_prompt_assembly` (async)

Phase 7.6d-4 — focused minimal port.

The OpenClaw source is tightly coupled to the prompt assembly
pipeline (system-prompt, user message, tools, and tool-result
projection). The Python port keeps the public surface and
delegates the heavy work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt prompt-assembly shape.
EmbeddedAttemptPromptAssembly = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the assemble-prompt step.
_ASSEMBLE_PROMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_assemble_prompt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom assemble-prompt hook."""
    global _ASSEMBLE_PROMPT
    _ASSEMBLE_PROMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_prompt_assembly(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptAssembly:
    """Assemble the prompt for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptPromptAssembly`
    (``attempt-prompt-assembly.ts``).
    """
    assembled: Any = await _maybe_await(
        _ASSEMBLE_PROMPT(dict(input_obj or {}))
    )
    if not isinstance(assembled, dict):
        assembled = {}
    return {
        "systemPromptText": assembled.get("systemPromptText"),
        "messages": assembled.get("messages") or [],
        "tools": assembled.get("tools") or [],
        "prompt": assembled.get("prompt"),
        "report": assembled.get("report"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptPromptAssembly",
    "prepare_embedded_attempt_prompt_assembly",
    "set_assemble_prompt_hook",
]
