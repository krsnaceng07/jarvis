"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_context — prepare the prompt context for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-context.ts``.

Public surface:

- :func:`prepare_embedded_attempt_prompt_context`

Phase 7.6d-4 — focused minimal port.

The OpenClaw source is tightly coupled to the boundary-timestamp,
user-message-boundary, and tool-result prompt-projection layers.
The Python port keeps the public surface and delegates the heavy
work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt prompt-context shape.
EmbeddedAttemptPromptContext = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the resolve-boundary-timestamp step.
_RESOLVE_BOUNDARY_TIMESTAMP: Callable[[Dict[str, Any]], Any] = lambda _p: None
_DEFAULT_RESOLVE_BOUNDARY_TIMESTAMP = _RESOLVE_BOUNDARY_TIMESTAMP


def set_resolve_boundary_timestamp_hook(
    hook: Callable[[Dict[str, Any]], Any] | None,
) -> None:
    """Install a custom resolve-boundary-timestamp hook."""
    global _RESOLVE_BOUNDARY_TIMESTAMP
    _RESOLVE_BOUNDARY_TIMESTAMP = (
        _DEFAULT_RESOLVE_BOUNDARY_TIMESTAMP if hook is None else hook
    )


#: Hook for the resolve-user-message-boundary step.
_RESOLVE_USER_MESSAGE_BOUNDARY: Callable[[Dict[str, Any]], Any] = lambda _p: {}
_DEFAULT_RESOLVE_USER_MESSAGE_BOUNDARY = _RESOLVE_USER_MESSAGE_BOUNDARY


def set_resolve_user_message_boundary_hook(
    hook: Callable[[Dict[str, Any]], Any] | None,
) -> None:
    """Install a custom resolve-user-message-boundary hook."""
    global _RESOLVE_USER_MESSAGE_BOUNDARY
    _RESOLVE_USER_MESSAGE_BOUNDARY = (
        _DEFAULT_RESOLVE_USER_MESSAGE_BOUNDARY if hook is None else hook
    )


#: Hook for the build-tool-result-prompt-projection step.
_BUILD_TOOL_RESULT_PROMPT_PROJECTION: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}
_DEFAULT_BUILD_TOOL_RESULT_PROMPT_PROJECTION = _BUILD_TOOL_RESULT_PROMPT_PROJECTION


def set_build_tool_result_prompt_projection_hook(
    hook: Callable[[Dict[str, Any]], Any] | None,
) -> None:
    """Install a custom build-tool-result-prompt-projection hook."""
    global _BUILD_TOOL_RESULT_PROMPT_PROJECTION
    _BUILD_TOOL_RESULT_PROMPT_PROJECTION = (
        _DEFAULT_BUILD_TOOL_RESULT_PROMPT_PROJECTION if hook is None else hook
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_prompt_context(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptContext:
    """Prepare the prompt context for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptPromptContext`
    (``attempt-prompt-context.ts``).
    """
    boundary = _RESOLVE_BOUNDARY_TIMESTAMP(dict(input_obj or {}))
    user_boundary = _RESOLVE_USER_MESSAGE_BOUNDARY(dict(input_obj or {}))
    projection = _BUILD_TOOL_RESULT_PROMPT_PROJECTION(dict(input_obj or {}))
    return {
        "boundary": boundary,
        "userBoundary": user_boundary,
        "projection": projection,
    }


__all__ = [
    "EmbeddedAttemptPromptContext",
    "prepare_embedded_attempt_prompt_context",
    "set_build_tool_result_prompt_projection_hook",
    "set_resolve_boundary_timestamp_hook",
    "set_resolve_user_message_boundary_hook",
]
