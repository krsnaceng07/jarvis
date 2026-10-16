"""jarvis.agents.embedded_agent_runner.run.run_attempt_dispatch — dispatch an embedded-run attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/run-attempt-dispatch.ts``.

Public surface:

- :func:`dispatch_embedded_run_attempt` (async)

Phase 7.6g — focused minimal port.

The OpenClaw source is large (~16K) and tightly couples attempt
orchestration with prompt-dispatch and stream-settlement. The
Python port keeps the public surface and delegates the heavy
work to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Run-attempt input shape.
RunAttemptInput = Dict[str, Any]


#: Run-attempt dispatch result shape.
RunAttemptDispatchResult = Dict[str, Any]


async def _default_dispatch_embedded_run_attempt(params: Dict[str, Any]) -> Any:
    from .attempt import run_embedded_attempt

    return await run_embedded_attempt(params)


#: Installable hook for the dispatch-embedded-run-attempt step.
_DISPATCH_EMBEDDED_RUN_ATTEMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = _default_dispatch_embedded_run_attempt


def set_dispatch_embedded_run_attempt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom dispatchEmbeddedRunAttempt hook."""
    global _DISPATCH_EMBEDDED_RUN_ATTEMPT
    _DISPATCH_EMBEDDED_RUN_ATTEMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def dispatch_embedded_run_attempt(
    input_obj: RunAttemptInput,
) -> RunAttemptDispatchResult:
    """Dispatch an embedded-run attempt.

    Mirrors :func:`dispatchEmbeddedRunAttempt`
    (``run-attempt-dispatch.ts``).
    """
    result: Any = await _maybe_await(
        _DISPATCH_EMBEDDED_RUN_ATTEMPT(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "attemptResult": result.get("attemptResult"),
        "terminal": result.get("terminal"),
        "outcome": result.get("outcome", "complete"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "RunAttemptDispatchResult",
    "RunAttemptInput",
    "dispatch_embedded_run_attempt",
    "set_dispatch_embedded_run_attempt_hook",
]
