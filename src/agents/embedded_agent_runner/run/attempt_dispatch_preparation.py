"""jarvis.agents.embedded_agent_runner.run.attempt_dispatch_preparation — prepare and dispatch the embedded-run attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-dispatch-preparation.ts``.

Public surface:

- :func:`prepare_and_dispatch_embedded_run_attempt` (async)

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Installable hook for the prepare-and-dispatch-embedded-run-attempt step.
_PREPARE_AND_DISPATCH_EMBEDDED_RUN_ATTEMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_and_dispatch_embedded_run_attempt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepareAndDispatchEmbeddedRunAttempt hook."""
    global _PREPARE_AND_DISPATCH_EMBEDDED_RUN_ATTEMPT
    _PREPARE_AND_DISPATCH_EMBEDDED_RUN_ATTEMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_and_dispatch_embedded_run_attempt(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Prepare and dispatch the embedded-run attempt.

    Mirrors :func:`prepareAndDispatchEmbeddedRunAttempt`
    (``attempt-dispatch-preparation.ts``).
    """
    result: Any = await _maybe_await(
        _PREPARE_AND_DISPATCH_EMBEDDED_RUN_ATTEMPT(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "prepared": bool(result.get("prepared", True)),
        "dispatched": bool(result.get("dispatched", False)),
        "result": result.get("result"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "prepare_and_dispatch_embedded_run_attempt",
    "set_prepare_and_dispatch_embedded_run_attempt_hook",
]
