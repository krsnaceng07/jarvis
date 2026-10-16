"""jarvis.agents.embedded_agent_runner.run.trigger_policy — embedded-run trigger policy.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/trigger-policy.ts``.

Public surface:

- :func:`resolve_trigger_policy`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the resolve-trigger-policy step.
_RESOLVE_TRIGGER_POLICY: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_resolve_trigger_policy_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveTriggerPolicy hook."""
    global _RESOLVE_TRIGGER_POLICY
    _RESOLVE_TRIGGER_POLICY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_trigger_policy(params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the trigger policy for a run.

    Mirrors :func:`resolveTriggerPolicy` (``trigger-policy.ts``).
    """
    return _RESOLVE_TRIGGER_POLICY(dict(params or {}))


__all__ = [
    "resolve_trigger_policy",
    "set_resolve_trigger_policy_hook",
]
