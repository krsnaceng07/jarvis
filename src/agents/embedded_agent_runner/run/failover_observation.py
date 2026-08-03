"""jarvis.agents.embedded_agent_runner.run.failover_observation — create the failover-decision logger.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/failover-observation.ts``.

Public surface:

- :func:`create_failover_decision_logger`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the create-failover-decision-logger step.
_CREATE_FAILOVER_DECISION_LOGGER: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_create_failover_decision_logger_failover_observation_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createFailoverDecisionLogger hook."""
    global _CREATE_FAILOVER_DECISION_LOGGER
    _CREATE_FAILOVER_DECISION_LOGGER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_failover_decision_logger(
    params: Dict[str, Any],
) -> Any:
    """Create the failover-decision logger.

    Mirrors :func:`createFailoverDecisionLogger`
    (``failover-observation.ts``).
    """
    return _CREATE_FAILOVER_DECISION_LOGGER(dict(params or {}))


__all__ = [
    "create_failover_decision_logger",
    "set_create_failover_decision_logger_failover_observation_hook",
]
