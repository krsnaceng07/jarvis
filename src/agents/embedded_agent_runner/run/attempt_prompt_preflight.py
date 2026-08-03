"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_preflight — preflight mid-turn and pre-prompt checks for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-preflight.ts``.

Public surface:

Functions:

- :func:`handle_embedded_attempt_mid_turn_precheck`
- :func:`prepare_embedded_attempt_prompt_preflight` (async)

Phase 7.6d-4 — focused minimal port.

The OpenClaw source is tightly coupled to the pre-prompt
context-budget, mid-turn precheck, and precheck-result layers.
The Python port keeps the public surface and delegates the heavy
work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Mid-turn precheck outcome.
MidTurnPrecheckOutcome = Dict[str, Any]


#: Prompt preflight shape.
EmbeddedAttemptPromptPreflight = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the build-pre-prompt-context-budget-status step.
_BUILD_PRE_PROMPT_CONTEXT_BUDGET_STATUS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_pre_prompt_context_budget_status_preflight_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom build-pre-prompt-context-budget-status hook."""
    global _BUILD_PRE_PROMPT_CONTEXT_BUDGET_STATUS
    _BUILD_PRE_PROMPT_CONTEXT_BUDGET_STATUS = hook


#: Hook for the format-pre-prompt-precheck-log step.
_FORMAT_PRE_PROMPT_PRECHECK_LOG: Callable[[Dict[str, Any]], str] = lambda _p: ""


def set_format_pre_prompt_precheck_log_preflight_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom format-pre-prompt-precheck-log hook."""
    global _FORMAT_PRE_PROMPT_PRECHECK_LOG
    _FORMAT_PRE_PROMPT_PRECHECK_LOG = hook


#: Hook for the run-mid-turn-precheck step.
_RUN_MID_TURN_PRECHECK: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_run_mid_turn_precheck_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom run-mid-turn-precheck hook."""
    global _RUN_MID_TURN_PRECHECK
    _RUN_MID_TURN_PRECHECK = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_embedded_attempt_mid_turn_precheck(
    input_obj: Dict[str, Any],
) -> MidTurnPrecheckOutcome:
    """Handle the mid-turn precheck for an attempt.

    Mirrors :func:`handleEmbeddedAttemptMidTurnPrecheck`
    (``attempt-prompt-preflight.ts``).
    """
    return {
        "outcome": "continue",
        "contextBudgetStatus": _BUILD_PRE_PROMPT_CONTEXT_BUDGET_STATUS(
            dict(input_obj or {})
        ),
    }


async def prepare_embedded_attempt_prompt_preflight(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptPreflight:
    """Prepare the prompt preflight for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptPromptPreflight`
    (``attempt-prompt-preflight.ts``).
    """
    decision = input_obj.get("decision") or {}
    log_line = _FORMAT_PRE_PROMPT_PRECHECK_LOG(
        {"decision": decision, "input": input_obj}
    )
    return {
        "decision": decision,
        "logLine": log_line,
        "contextBudgetStatus": _BUILD_PRE_PROMPT_CONTEXT_BUDGET_STATUS(
            dict(input_obj or {})
        ),
    }


__all__ = [
    "EmbeddedAttemptPromptPreflight",
    "MidTurnPrecheckOutcome",
    "handle_embedded_attempt_mid_turn_precheck",
    "prepare_embedded_attempt_prompt_preflight",
    "set_build_pre_prompt_context_budget_status_preflight_hook",
    "set_format_pre_prompt_precheck_log_preflight_hook",
    "set_run_mid_turn_precheck_hook",
]
