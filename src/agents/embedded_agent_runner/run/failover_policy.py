"""jarvis.agents.embedded_agent_runner.run.failover_policy — resolve the failover decision for a run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/failover-policy.ts``.

Public surface:

Constants:

- :data:`MAX_BEFORE_AGENT_FINALIZE_REVISIONS`

Types:

- :data:`AssistantFailoverDecision`
- :data:`EmbeddedRunTerminalRetryState`

Functions:

- :func:`resolve_run_failover_decision`
- :func:`merge_retry_failover_reason`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Maximum before-agent-finalize revisions. Mirrors
#: :data:`MAX_BEFORE_AGENT_FINALIZE_REVISIONS`
#: (``failover-policy.ts``).
MAX_BEFORE_AGENT_FINALIZE_REVISIONS: int = 1


#: Assistant failover decision shape.
AssistantFailoverDecision = Dict[str, Any]


#: Embedded-run terminal retry state shape.
EmbeddedRunTerminalRetryState = Dict[str, Any]


#: Installable hook for the resolve-run-failover-decision step.
_RESOLVE_RUN_FAILOVER_DECISION: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_run_failover_decision_failover_policy_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveRunFailoverDecision hook."""
    global _RESOLVE_RUN_FAILOVER_DECISION
    _RESOLVE_RUN_FAILOVER_DECISION = hook


#: Installable hook for the merge-retry-failover-reason step.
_MERGE_RETRY_FAILOVER_REASON: Callable[
    [Any, Any], Any
] = lambda cur, _new: cur


def set_merge_retry_failover_reason_failover_policy_hook(
    hook: Callable[[Any, Any], Any],
) -> None:
    """Install a custom mergeRetryFailoverReason hook."""
    global _MERGE_RETRY_FAILOVER_REASON
    _MERGE_RETRY_FAILOVER_REASON = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_run_failover_decision(
    params: Dict[str, Any],
) -> AssistantFailoverDecision:
    """Resolve the run failover decision.

    Mirrors :func:`resolveRunFailoverDecision`
    (``failover-policy.ts``).
    """
    decision = _RESOLVE_RUN_FAILOVER_DECISION(dict(params or {}))
    if not isinstance(decision, dict):
        decision = {}
    return {
        "action": decision.get("action", "continue_normal"),
        "reason": decision.get("reason"),
    }


def merge_retry_failover_reason(
    current: Any,
    new: Any,
) -> Any:
    """Merge a retry-failover reason.

    Mirrors :func:`mergeRetryFailoverReason`
    (``failover-policy.ts``).
    """
    return _MERGE_RETRY_FAILOVER_REASON(current, new)


__all__ = [
    "AssistantFailoverDecision",
    "EmbeddedRunTerminalRetryState",
    "MAX_BEFORE_AGENT_FINALIZE_REVISIONS",
    "merge_retry_failover_reason",
    "resolve_run_failover_decision",
    "set_merge_retry_failover_reason_failover_policy_hook",
    "set_resolve_run_failover_decision_failover_policy_hook",
]
