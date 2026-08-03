"""jarvis.agents.embedded_agent_runner.run.recovery_message_action_capability — recovery-message action-capability helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/recovery-message-action-capability.ts``.

Public surface:

- :func:`has_recovery_message_action_capability`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the has-recovery-message-action-capability step.
_HAS_RECOVERY_MESSAGE_ACTION_CAPABILITY: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_has_recovery_message_action_capability_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom hasRecoveryMessageActionCapability hook."""
    global _HAS_RECOVERY_MESSAGE_ACTION_CAPABILITY
    _HAS_RECOVERY_MESSAGE_ACTION_CAPABILITY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_recovery_message_action_capability(
    params: Dict[str, Any],
) -> bool:
    """Return True when the recovery message has the action capability.

    Mirrors :func:`hasRecoveryMessageActionCapability`
    (``recovery-message-action-capability.ts``).
    """
    return _HAS_RECOVERY_MESSAGE_ACTION_CAPABILITY(dict(params or {}))


__all__ = [
    "has_recovery_message_action_capability",
    "set_has_recovery_message_action_capability_hook",
]
