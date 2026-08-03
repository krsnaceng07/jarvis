"""jarvis.agents.embedded_agent_runner.run.failover_retry_controller — control the failover retry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/failover-retry-controller.ts``.

Public surface:

Functions:

- :func:`should_retry_after_failover`
- :func:`record_failover_retry`
- :func:`clear_failover_retries`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Per-run failover-retry counter.
_FAILOVER_RETRY_COUNTER: Dict[str, int] = {}


#: Installable hook for the should-retry-after-failover step.
_SHOULD_RETRY_AFTER_FAILOVER: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_retry_after_failover_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldRetryAfterFailover hook."""
    global _SHOULD_RETRY_AFTER_FAILOVER
    _SHOULD_RETRY_AFTER_FAILOVER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_retry_after_failover(
    params: Dict[str, Any],
) -> bool:
    """Return True when the run should retry after a failover.

    Mirrors :func:`shouldRetryAfterFailover`
    (``failover-retry-controller.ts``).
    """
    return _SHOULD_RETRY_AFTER_FAILOVER(dict(params or {}))


def record_failover_retry(run_id: Optional[str]) -> int:
    """Record a failover retry for a run.

    Mirrors :func:`recordFailoverRetry`
    (``failover-retry-controller.ts``).
    """
    if not run_id:
        return 0
    _FAILOVER_RETRY_COUNTER[run_id] = (
        _FAILOVER_RETRY_COUNTER.get(run_id, 0) + 1
    )
    return _FAILOVER_RETRY_COUNTER[run_id]


def clear_failover_retries(run_id: Optional[str]) -> None:
    """Clear the failover-retries for a run.

    Mirrors :func:`clearFailoverRetries`
    (``failover-retry-controller.ts``).
    """
    if not run_id:
        return
    _FAILOVER_RETRY_COUNTER.pop(run_id, None)


__all__ = [
    "clear_failover_retries",
    "record_failover_retry",
    "set_should_retry_after_failover_hook",
    "should_retry_after_failover",
]
