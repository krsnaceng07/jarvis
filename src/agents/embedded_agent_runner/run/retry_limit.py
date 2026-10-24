"""jarvis.agents.embedded_agent_runner.run.retry_limit — check the retry-limit for a run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/retry-limit.ts``.

Public surface:

- :func:`is_within_retry_limit`
- :func:`handle_retry_limit_exhaustion`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


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


def handle_retry_limit_exhaustion(
    message: str,
    decision: Dict[str, Any],
    provider: str,
    model: str,
    duration_ms: int,
    agent_meta: Dict[str, Any],
    profile_id: Optional[str] = None,
    replay_invalid: bool = False,
    liveness_state: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Handle exhaustion of retry budget.

    Mirrors :func:`handleRetryLimitExhaustion` in ``retry-limit.ts``.
    """
    text = (
        "Request failed after repeated internal retries. "
        "Please try again, or use /new to start a fresh session."
    )
    return {
        "payloads": [
            {
                "text": text,
                "isError": True,
            }
        ],
        "meta": {
            "durationMs": duration_ms,
            "agentMeta": agent_meta,
            "finalAssistantVisibleText": text,
            "finalAssistantRawText": text,
            "error": {"kind": "retry_limit", "message": message},
        },
    }


__all__ = [
    "handle_retry_limit_exhaustion",
    "is_within_retry_limit",
    "set_is_within_retry_limit_hook",
]
