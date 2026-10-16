"""jarvis.agents.embedded_agent_runner.run.attempt_llm_boundary — normalize messages for the LLM boundary.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.llm-boundary.ts``.

Public surface:

Functions:

- :func:`normalize_messages_for_llm_boundary`
- :func:`normalize_messages_for_current_prompt_boundary`
- :func:`normalize_current_prompt_text_for_llm_boundary`
- :func:`install_runtime_context_message_for_prompt`
- :func:`install_model_prompt_transform`

Phase 7.6f-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List


#: Installable hook for the normalize-messages-for-llm-boundary step.
_NORMALIZE_MESSAGES_FOR_LLM_BOUNDARY: Callable[
    [List[Dict[str, Any]]], List[Dict[str, Any]]
] = lambda messages: list(messages or [])


def set_normalize_messages_for_llm_boundary_hook(
    hook: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> None:
    """Install a custom normalizeMessagesForLlmBoundary hook."""
    global _NORMALIZE_MESSAGES_FOR_LLM_BOUNDARY
    _NORMALIZE_MESSAGES_FOR_LLM_BOUNDARY = hook


#: Installable hook for the normalize-messages-for-current-prompt-boundary step.
_NORMALIZE_MESSAGES_FOR_CURRENT_PROMPT_BOUNDARY: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_normalize_messages_for_current_prompt_boundary_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom normalizeMessagesForCurrentPromptBoundary hook."""
    global _NORMALIZE_MESSAGES_FOR_CURRENT_PROMPT_BOUNDARY
    _NORMALIZE_MESSAGES_FOR_CURRENT_PROMPT_BOUNDARY = hook


#: Installable hook for the normalize-current-prompt-text-for-llm-boundary step.
_NORMALIZE_CURRENT_PROMPT_TEXT_FOR_LLM_BOUNDARY: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_normalize_current_prompt_text_for_llm_boundary_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom normalizeCurrentPromptTextForLlmBoundary hook."""
    global _NORMALIZE_CURRENT_PROMPT_TEXT_FOR_LLM_BOUNDARY
    _NORMALIZE_CURRENT_PROMPT_TEXT_FOR_LLM_BOUNDARY = hook


#: Installable hook for the install-runtime-context-message-for-prompt step.
_INSTALL_RUNTIME_CONTEXT_MESSAGE_FOR_PROMPT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_install_runtime_context_message_for_prompt_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom installRuntimeContextMessageForPrompt hook."""
    global _INSTALL_RUNTIME_CONTEXT_MESSAGE_FOR_PROMPT
    _INSTALL_RUNTIME_CONTEXT_MESSAGE_FOR_PROMPT = hook


#: Installable hook for the install-model-prompt-transform step.
_INSTALL_MODEL_PROMPT_TRANSFORM: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_install_model_prompt_transform_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom installModelPromptTransform hook."""
    global _INSTALL_MODEL_PROMPT_TRANSFORM
    _INSTALL_MODEL_PROMPT_TRANSFORM = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_messages_for_llm_boundary(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Normalize messages for the LLM boundary.

    Mirrors :func:`normalizeMessagesForLlmBoundary`
    (``attempt.llm-boundary.ts``).
    """
    return _NORMALIZE_MESSAGES_FOR_LLM_BOUNDARY(messages or [])


def normalize_messages_for_current_prompt_boundary(
    params: Dict[str, Any],
) -> Any:
    """Normalize messages for the current prompt boundary.

    Mirrors :func:`normalizeMessagesForCurrentPromptBoundary`
    (``attempt.llm-boundary.ts``).
    """
    return _NORMALIZE_MESSAGES_FOR_CURRENT_PROMPT_BOUNDARY(
        dict(params or {})
    )


def normalize_current_prompt_text_for_llm_boundary(
    params: Dict[str, Any],
) -> Any:
    """Normalize the current prompt text for the LLM boundary.

    Mirrors :func:`normalizeCurrentPromptTextForLlmBoundary`
    (``attempt.llm-boundary.ts``).
    """
    return _NORMALIZE_CURRENT_PROMPT_TEXT_FOR_LLM_BOUNDARY(
        dict(params or {})
    )


def install_runtime_context_message_for_prompt(
    params: Dict[str, Any],
) -> Any:
    """Install the runtime-context message for the prompt.

    Mirrors :func:`installRuntimeContextMessageForPrompt`
    (``attempt.llm-boundary.ts``).
    """
    return _INSTALL_RUNTIME_CONTEXT_MESSAGE_FOR_PROMPT(dict(params or {}))


def install_model_prompt_transform(
    params: Dict[str, Any],
) -> Any:
    """Install the model-prompt transform.

    Mirrors :func:`installModelPromptTransform`
    (``attempt.llm-boundary.ts``).
    """
    return _INSTALL_MODEL_PROMPT_TRANSFORM(dict(params or {}))


__all__ = [
    "install_model_prompt_transform",
    "install_runtime_context_message_for_prompt",
    "normalize_current_prompt_text_for_llm_boundary",
    "normalize_messages_for_current_prompt_boundary",
    "normalize_messages_for_llm_boundary",
    "set_install_model_prompt_transform_hook",
    "set_install_runtime_context_message_for_prompt_hook",
    "set_normalize_current_prompt_text_for_llm_boundary_hook",
    "set_normalize_messages_for_current_prompt_boundary_hook",
    "set_normalize_messages_for_llm_boundary_hook",
]
