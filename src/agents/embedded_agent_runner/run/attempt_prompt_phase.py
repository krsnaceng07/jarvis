"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_phase — run the prompt phase of an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-phase.ts``.

Public surface:

- :func:`run_embedded_attempt_prompt_phase` (async)

Phase 7.6d-4 — focused minimal port.

The OpenClaw source is tightly coupled to the prompt-submit,
stream-prepare, prompt-dispatch, before-agent-run, and
orphan-repair layers. The Python port keeps the public surface
and delegates the heavy work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt prompt-phase shape.
EmbeddedAttemptPromptPhase = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the run-prompt-submit step.
_RUN_PROMPT_SUBMIT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)
_DEFAULT_RUN_PROMPT_SUBMIT = _RUN_PROMPT_SUBMIT


def set_run_prompt_submit_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom run-prompt-submit hook."""
    global _RUN_PROMPT_SUBMIT
    _RUN_PROMPT_SUBMIT = _DEFAULT_RUN_PROMPT_SUBMIT if hook is None else hook


#: Hook for the prepare-attempt-stream-runtime step.
_PREPARE_ATTEMPT_STREAM_RUNTIME: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)
_DEFAULT_PREPARE_ATTEMPT_STREAM_RUNTIME = _PREPARE_ATTEMPT_STREAM_RUNTIME


def set_prepare_attempt_stream_runtime_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom prepare-attempt-stream-runtime hook."""
    global _PREPARE_ATTEMPT_STREAM_RUNTIME
    _PREPARE_ATTEMPT_STREAM_RUNTIME = (
        _DEFAULT_PREPARE_ATTEMPT_STREAM_RUNTIME if hook is None else hook
    )


#: Hook for the run-prompt-dispatch step.
_RUN_PROMPT_DISPATCH: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)
_DEFAULT_RUN_PROMPT_DISPATCH = _RUN_PROMPT_DISPATCH


def set_run_prompt_dispatch_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]] | None,
) -> None:
    """Install a custom run-prompt-dispatch hook."""
    global _RUN_PROMPT_DISPATCH
    _RUN_PROMPT_DISPATCH = _DEFAULT_RUN_PROMPT_DISPATCH if hook is None else hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_embedded_attempt_prompt_phase(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptPromptPhase:
    """Run the prompt phase of an attempt.

    Mirrors :func:`runEmbeddedAttemptPromptPhase`
    (``attempt-prompt-phase.ts``).
    """
    preflight: Any = await _maybe_await(
        _RUN_PROMPT_SUBMIT(dict(input_obj or {}))
    )
    stream_runtime: Any = await _maybe_await(
        _PREPARE_ATTEMPT_STREAM_RUNTIME(
            {"input": input_obj, "preflight": preflight}
        )
    )
    dispatch: Any = await _maybe_await(
        _RUN_PROMPT_DISPATCH(
            {"input": input_obj, "preflight": preflight, "streamRuntime": stream_runtime}
        )
    )
    if not isinstance(preflight, dict):
        preflight = {}
    if not isinstance(stream_runtime, dict):
        stream_runtime = {}
    if not isinstance(dispatch, dict):
        dispatch = {}
    return {
        "preflight": preflight,
        "streamRuntime": stream_runtime,
        "dispatch": dispatch,
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptPromptPhase",
    "run_embedded_attempt_prompt_phase",
    "set_prepare_attempt_stream_runtime_phase_hook",
    "set_run_prompt_dispatch_hook",
    "set_run_prompt_submit_hook",
]
