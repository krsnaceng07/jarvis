"""jarvis.agents.embedded_agent_runner.run.compaction_retry_aggregate_timeout — wait for the compaction retry with an aggregate timeout.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/compaction-retry-aggregate-timeout.ts``.

Public surface:

Functions:

- :func:`has_active_compaction_retry_work`
- :func:`wait_for_compaction_retry_with_aggregate_timeout` (async)

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the has-active-compaction-retry-work step.
_HAS_ACTIVE_COMPACTION_RETRY_WORK: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_has_active_compaction_retry_work_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom hasActiveCompactionRetryWork hook."""
    global _HAS_ACTIVE_COMPACTION_RETRY_WORK
    _HAS_ACTIVE_COMPACTION_RETRY_WORK = hook


#: Installable hook for the wait-for-compaction-retry-with-aggregate-timeout step.
_WAIT_FOR_COMPACTION_RETRY_WITH_AGGREGATE_TIMEOUT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_wait_for_compaction_retry_with_aggregate_timeout_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom waitForCompactionRetryWithAggregateTimeout hook."""
    global _WAIT_FOR_COMPACTION_RETRY_WITH_AGGREGATE_TIMEOUT
    _WAIT_FOR_COMPACTION_RETRY_WITH_AGGREGATE_TIMEOUT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_active_compaction_retry_work(
    params: Dict[str, Any],
) -> bool:
    """Return True when there is active compaction-retry work.

    Mirrors :func:`hasActiveCompactionRetryWork`
    (``compaction-retry-aggregate-timeout.ts``).
    """
    return _HAS_ACTIVE_COMPACTION_RETRY_WORK(dict(params or {}))


async def wait_for_compaction_retry_with_aggregate_timeout(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Wait for the compaction retry with an aggregate timeout.

    Mirrors :func:`waitForCompactionRetryWithAggregateTimeout`
    (``compaction-retry-aggregate-timeout.ts``).
    """
    result: Any = await _maybe_await(
        _WAIT_FOR_COMPACTION_RETRY_WITH_AGGREGATE_TIMEOUT(
            dict(params or {})
        )
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "completed": bool(result.get("completed", False)),
        "timedOut": bool(result.get("timedOut", False)),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "has_active_compaction_retry_work",
    "set_has_active_compaction_retry_work_hook",
    "set_wait_for_compaction_retry_with_aggregate_timeout_hook",
    "wait_for_compaction_retry_with_aggregate_timeout",
]
