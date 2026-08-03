"""jarvis.agents.embedded_agent_runner.run.attempt_normalization — normalize an embedded run attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-normalization.ts``.

Public surface:

- :func:`normalize_embedded_run_attempt` (async)

Phase 7.6d-3 — focused minimal port.

The OpenClaw source is tightly coupled to the prompt normalizer,
message-list normalizer, and run-attempt result-projection layers.
The Python port keeps the public surface and delegates the heavy
work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Normalized run attempt.
NormalizedEmbeddedRunAttempt = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the normalize-prompt step.
_NORMALIZE_PROMPT: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_normalize_prompt_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom normalize-prompt hook."""
    global _NORMALIZE_PROMPT
    _NORMALIZE_PROMPT = hook


#: Hook for the normalize-message-list step.
_NORMALIZE_MESSAGE_LIST: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_normalize_message_list_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom normalize-message-list hook."""
    global _NORMALIZE_MESSAGE_LIST
    _NORMALIZE_MESSAGE_LIST = hook


#: Hook for the project-run-attempt-result step.
_PROJECT_RUN_ATTEMPT_RESULT: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_project_run_attempt_result_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom project-run-attempt-result hook."""
    global _PROJECT_RUN_ATTEMPT_RESULT
    _PROJECT_RUN_ATTEMPT_RESULT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def normalize_embedded_run_attempt(
    input_obj: Dict[str, Any],
) -> NormalizedEmbeddedRunAttempt:
    """Normalize an embedded run attempt.

    Mirrors :func:`normalizeEmbeddedRunAttempt`
    (``attempt-normalization.ts``).
    """
    attempt = input_obj.get("attempt") or {}
    prompt = _NORMALIZE_PROMPT({"attempt": attempt, "input": input_obj})
    messages = _NORMALIZE_MESSAGE_LIST({"attempt": attempt, "input": input_obj})
    projection = _PROJECT_RUN_ATTEMPT_RESULT(
        {"attempt": attempt, "input": input_obj, "prompt": prompt, "messages": messages}
    )
    if not isinstance(projection, dict):
        projection = {}
    return {
        "attemptId": attempt.get("runId"),
        "prompt": prompt,
        "messages": messages,
        "projection": projection,
    }


__all__ = [
    "NormalizedEmbeddedRunAttempt",
    "normalize_embedded_run_attempt",
    "set_normalize_message_list_hook",
    "set_normalize_prompt_hook",
    "set_project_run_attempt_result_hook",
]
