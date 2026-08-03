"""jarvis.agents.embedded_agent_runner.run.attempt_before_agent_run — run the before-agent-run hook for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-before-agent-run.ts``.

Public surface:

- :func:`run_embedded_attempt_before_agent_run` (async)

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt before-agent-run shape.
EmbeddedAttemptBeforeAgentRun = Dict[str, Any]


#: Installable hook for the before-agent-run step.
_RUN_BEFORE_AGENT_RUN: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_run_before_agent_run_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom run-embedded-attempt-before-agent-run hook."""
    global _RUN_BEFORE_AGENT_RUN
    _RUN_BEFORE_AGENT_RUN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_embedded_attempt_before_agent_run(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptBeforeAgentRun:
    """Run the before-agent-run hook for an attempt.

    Mirrors :func:`runEmbeddedAttemptBeforeAgentRun`
    (``attempt-before-agent-run.ts``).
    """
    result: Any = await _maybe_await(
        _RUN_BEFORE_AGENT_RUN(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "beforeAgentRunResult": result.get("beforeAgentRunResult"),
        "blocked": bool(result.get("blocked", False)),
        "blockedBy": result.get("blockedBy"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptBeforeAgentRun",
    "run_embedded_attempt_before_agent_run",
    "set_run_before_agent_run_hook",
]
