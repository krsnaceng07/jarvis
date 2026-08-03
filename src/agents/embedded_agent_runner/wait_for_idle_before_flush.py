"""jarvis.agents.embedded_agent_runner.wait_for_idle_before_flush — idle wait for tool-result streams.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/wait-for-idle-before-flush.ts``.

Public surface:

- :func:`flush_pending_tool_results_after_idle`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional


DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS = 30_000

_flush_pending_tool_results_after_idle_hook = None


def set_flush_pending_tool_results_after_idle_hook(fn) -> None:
    global _flush_pending_tool_results_after_idle_hook
    _flush_pending_tool_results_after_idle_hook = fn


async def _wait_for_agent_idle_best_effort(
    agent: Any,
    timeout_ms: int,
) -> bool:
    wait_for_idle = getattr(agent, "waitForIdle", None)
    if not callable(wait_for_idle):
        return False
    if timeout_ms <= 0:
        # Immediate timeout — skip the wait, return false (best-effort).
        return True
    try:
        await asyncio.wait_for(
            asyncio.ensure_future(wait_for_idle()),
            timeout=timeout_ms / 1000.0,
        )
        return True
    except (asyncio.TimeoutError, Exception):
        return False


async def flush_pending_tool_results_after_idle(opts: dict) -> None:
    """Wait for the agent to become idle, then flush any pending tool results.

    Mirrors :func:`flushPendingToolResultsAfterIdle`
    (``wait-for-idle-before-flush.ts``).
    """
    if _flush_pending_tool_results_after_idle_hook is not None:
        result = _flush_pending_tool_results_after_idle_hook(opts)
        if hasattr(result, "__await__"):
            await result  # type: ignore[func-returns-value]
        return
    agent = opts.get("agent")
    session_manager = opts.get("sessionManager")
    timeout_ms = opts.get("timeoutMs", DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS)
    if timeout_ms > 0:
        await _wait_for_agent_idle_best_effort(agent, timeout_ms)
    if session_manager is not None:
        flush = getattr(session_manager, "flushPendingToolResults", None)
        if callable(flush):
            try:
                flush()
            except Exception:
                pass


__all__ = [
    "DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS",
    "flush_pending_tool_results_after_idle",
    "set_flush_pending_tool_results_after_idle_hook",
]
