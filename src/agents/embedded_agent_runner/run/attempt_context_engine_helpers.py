"""jarvis.agents.embedded_agent_runner.run.attempt_context_engine_helpers — context-engine helper functions for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.context-engine-helpers.ts``.

Public surface:

Types:

- :data:`AttemptContextEngine`

Functions:

- :func:`resolve_attempt_bootstrap_context` (async)
- :func:`build_context_engine_prompt_cache_info`
- :func:`find_current_attempt_assistant_message`
- :func:`resolve_prompt_cache_touch_timestamp`
- :func:`build_loop_prompt_cache_info`

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional


#: Attempt context-engine shape.
AttemptContextEngine = Any


#: Installable hook for the resolve-attempt-bootstrap-context step.
_RESOLVE_ATTEMPT_BOOTSTRAP_CONTEXT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_resolve_attempt_bootstrap_context_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom resolveAttemptBootstrapContext hook."""
    global _RESOLVE_ATTEMPT_BOOTSTRAP_CONTEXT
    _RESOLVE_ATTEMPT_BOOTSTRAP_CONTEXT = hook


#: Installable hook for the build-context-engine-prompt-cache-info step.
_BUILD_CONTEXT_ENGINE_PROMPT_CACHE_INFO: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_context_engine_prompt_cache_info_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildContextEnginePromptCacheInfo hook."""
    global _BUILD_CONTEXT_ENGINE_PROMPT_CACHE_INFO
    _BUILD_CONTEXT_ENGINE_PROMPT_CACHE_INFO = hook


#: Installable hook for the find-current-attempt-assistant-message step.
_FIND_CURRENT_ATTEMPT_ASSISTANT_MESSAGE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_find_current_attempt_assistant_message_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom findCurrentAttemptAssistantMessage hook."""
    global _FIND_CURRENT_ATTEMPT_ASSISTANT_MESSAGE
    _FIND_CURRENT_ATTEMPT_ASSISTANT_MESSAGE = hook


#: Installable hook for the resolve-prompt-cache-touch-timestamp step.
_RESOLVE_PROMPT_CACHE_TOUCH_TIMESTAMP: Callable[
    [Dict[str, Any]], Any
] = lambda _p: 0


def set_resolve_prompt_cache_touch_timestamp_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolvePromptCacheTouchTimestamp hook."""
    global _RESOLVE_PROMPT_CACHE_TOUCH_TIMESTAMP
    _RESOLVE_PROMPT_CACHE_TOUCH_TIMESTAMP = hook


#: Installable hook for the build-loop-prompt-cache-info step.
_BUILD_LOOP_PROMPT_CACHE_INFO: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_loop_prompt_cache_info_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildLoopPromptCacheInfo hook."""
    global _BUILD_LOOP_PROMPT_CACHE_INFO
    _BUILD_LOOP_PROMPT_CACHE_INFO = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def resolve_attempt_bootstrap_context(
    params: Dict[str, Any],
) -> Any:
    """Resolve the attempt bootstrap context.

    Mirrors :func:`resolveAttemptBootstrapContext`
    (``attempt.context-engine-helpers.ts``).
    """
    return await _maybe_await(
        _RESOLVE_ATTEMPT_BOOTSTRAP_CONTEXT(dict(params or {}))
    )


def build_context_engine_prompt_cache_info(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the context-engine prompt-cache info.

    Mirrors :func:`buildContextEnginePromptCacheInfo`
    (``attempt.context-engine-helpers.ts``).
    """
    return _BUILD_CONTEXT_ENGINE_PROMPT_CACHE_INFO(dict(params or {}))


def find_current_attempt_assistant_message(
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Find the current attempt's assistant message.

    Mirrors :func:`findCurrentAttemptAssistantMessage`
    (``attempt.context-engine-helpers.ts``).
    """
    return _FIND_CURRENT_ATTEMPT_ASSISTANT_MESSAGE(dict(params or {}))


def resolve_prompt_cache_touch_timestamp(
    params: Dict[str, Any],
) -> int:
    """Resolve the prompt-cache touch timestamp.

    Mirrors :func:`resolvePromptCacheTouchTimestamp`
    (``attempt.context-engine-helpers.ts``).
    """
    return int(_RESOLVE_PROMPT_CACHE_TOUCH_TIMESTAMP(dict(params or {})) or 0)


def build_loop_prompt_cache_info(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the loop prompt-cache info.

    Mirrors :func:`buildLoopPromptCacheInfo`
    (``attempt.context-engine-helpers.ts``).
    """
    return _BUILD_LOOP_PROMPT_CACHE_INFO(dict(params or {}))


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AttemptContextEngine",
    "build_context_engine_prompt_cache_info",
    "build_loop_prompt_cache_info",
    "find_current_attempt_assistant_message",
    "resolve_attempt_bootstrap_context",
    "resolve_prompt_cache_touch_timestamp",
    "set_build_context_engine_prompt_cache_info_hook",
    "set_build_loop_prompt_cache_info_hook",
    "set_find_current_attempt_assistant_message_hook",
    "set_resolve_attempt_bootstrap_context_hook",
    "set_resolve_prompt_cache_touch_timestamp_hook",
]
