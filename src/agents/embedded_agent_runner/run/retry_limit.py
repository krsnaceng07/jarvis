"""jarvis.agents.embedded_agent_runner.run.retry_limit — check the retry-limit for a run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/retry-limit.ts``.

Public surface:

- :func:`is_within_retry_limit`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the is-within-retry-limit step.
_IS_WITHIN_RETRY_LIMIT: Callable[
    [Dict[str, Any]], bool
] = lambda _p: True


def set_is_within_retry_limit_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom isWithinRetryLimit hook."""
    global _IS_WITHIN_RETRY_LIMIT
    _IS_WITHIN_RETRY_LIMIT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_within_retry_limit(params: Dict[str, Any]) -> bool:
    """Return True when the run is within the retry-limit.

    Mirrors :func:`isWithinRetryLimit` (``retry-limit.ts``).
    """
    return _IS_WITHIN_RETRY_LIMIT(dict(params or {}))


__all__ = [
    "is_within_retry_limit",
    "set_is_within_retry_limit_hook",
]
