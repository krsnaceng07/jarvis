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

from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt prompt-assembly shape.
EmbeddedAttemptPromptAssembly = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the assemble-prompt step.
_ASSEMBLE_PROMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda input_obj: {
        "systemPromptText": input_obj.get("systemPromptText"),
        "messages": input_obj.get("messages") or [],
        "tools": input_obj.get("tools") or [],
        "prompt": input_obj.get("prompt"),
        "report": input_obj.get("report") or {},
    }
_DEFAULT_ASSEMBLE_PROMPT = _ASSEMBLE_PROMPT


def set_assemble_prompt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom assemble-prompt hook."""
    global _ASSEMBLE_PROMPT
    _ASSEMBLE_PROMPT = _DEFAULT_ASSEMBLE_PROMPT if hook is None else hook


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
        
    systemPromptText = assembled.get("systemPromptText")
    messages = assembled.get("messages") or []
    tools = assembled.get("tools") or []
    prompt = assembled.get("prompt")
    report = assembled.get("report")

    # Mirror OpenClaw: resolve before_prompt_build hook
    from .attempt_prompt_helpers import resolve_prompt_build_hook_result
    hook_result = await resolve_prompt_build_hook_result({
        "hookRunner": input_obj.get("hookRunner"),
        "hookCtx": input_obj.get("hookCtx", {}),
        "prompt": prompt,
        "messages": messages,
        "config": input_obj.get("config"),
    })
    
    if isinstance(hook_result, dict):
        if hook_result.get("prependContext") and prompt is not None:
            prompt = f"{hook_result['prependContext']}\n\n{prompt}"
        if hook_result.get("appendContext") and prompt is not None:
            prompt = f"{prompt}\n\n{hook_result['appendContext']}"
        if hook_result.get("systemPrompt"):
            systemPromptText = hook_result["systemPrompt"]

    return {
        "systemPromptText": systemPromptText,
        "messages": messages,
        "tools": tools,
        "prompt": prompt,
        "report": report,
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
