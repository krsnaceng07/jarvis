"""jarvis.agents.embedded_agent_runner.run.attempt_system_prompt_prepare — prepare the system prompt for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-system-prompt-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_system_prompt` (async)

Phase 7.6d-4 — focused minimal port.

The OpenClaw source is tightly coupled to the system-prompt
assembly, runtime-info builder, and identity-context layers. The
Python port keeps the public surface and delegates the heavy
work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from .attempt_system_prompt import build_attempt_system_prompt


#: Embedded-attempt system-prompt shape.
EmbeddedAttemptSystemPrompt = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the build-system-prompt step.
_BUILD_SYSTEM_PROMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: build_attempt_system_prompt(dict(_p or {}))
_DEFAULT_BUILD_SYSTEM_PROMPT = _BUILD_SYSTEM_PROMPT


def set_build_system_prompt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom build-system-prompt hook."""
    global _BUILD_SYSTEM_PROMPT
    _BUILD_SYSTEM_PROMPT = (
        _DEFAULT_BUILD_SYSTEM_PROMPT if hook is None else hook
    )


#: Hook for the build-runtime-info step.
_BUILD_RUNTIME_INFO: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_build_runtime_info_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom build-runtime-info hook."""
    global _BUILD_RUNTIME_INFO
    _BUILD_RUNTIME_INFO = hook


#: Hook for the resolve-identity-context step.
_RESOLVE_IDENTITY_CONTEXT: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_resolve_identity_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolve-identity-context hook."""
    global _RESOLVE_IDENTITY_CONTEXT
    _RESOLVE_IDENTITY_CONTEXT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_system_prompt(
    params: Dict[str, Any],
) -> EmbeddedAttemptSystemPrompt:
    """Prepare the system prompt for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSystemPrompt`
    (``attempt-system-prompt-prepare.ts``).
    """
    runtime_info = _BUILD_RUNTIME_INFO(dict(params or {}))
    identity = _RESOLVE_IDENTITY_CONTEXT(dict(params or {}))
    built: Any = await _maybe_await(
        _BUILD_SYSTEM_PROMPT(
            {
                "params": params,
                "runtimeInfo": runtime_info,
                "identity": identity,
            }
        )
    )
    if not isinstance(built, dict):
        built = {}
    return {
        "systemPromptText": built.get("text"),
        "systemPromptReport": built.get("report"),
        "runtimeInfo": runtime_info,
        "identity": identity,
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptSystemPrompt",
    "prepare_embedded_attempt_system_prompt",
    "set_build_runtime_info_hook",
    "set_build_system_prompt_hook",
    "set_resolve_identity_context_hook",
]
