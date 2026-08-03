"""jarvis.agents.embedded_agent_runner.run.attempt_client_tools — prepare client tools for one attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-client-tools.ts``.

Public surface:

- :func:`prepare_embedded_attempt_client_tools`

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the agent-session,
client-tool slot, and client-tool-policy layers. The Python port
keeps the public surface and delegates the heavy work to
installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Embedded-attempt client-tools shape.
EmbeddedAttemptClientTools = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the resolve-client-tool-policy step.
_RESOLVE_CLIENT_TOOL_POLICY: Callable[[Dict[str, Any]], Any] = lambda _p: None


def set_resolve_client_tool_policy_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolve-client-tool-policy hook."""
    global _RESOLVE_CLIENT_TOOL_POLICY
    _RESOLVE_CLIENT_TOOL_POLICY = hook


#: Hook for the create-client-tool-slots step.
_CREATE_CLIENT_TOOL_SLOTS: Callable[[Dict[str, Any]], List[Dict[str, Any]]] = (
    lambda _p: []
)


def set_create_client_tool_slots_hook(
    hook: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
) -> None:
    """Install a custom create-client-tool-slots hook."""
    global _CREATE_CLIENT_TOOL_SLOTS
    _CREATE_CLIENT_TOOL_SLOTS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_client_tools(
    params: Dict[str, Any],
) -> EmbeddedAttemptClientTools:
    """Prepare the client tools for one attempt.

    Mirrors :func:`prepareEmbeddedAttemptClientTools`
    (``attempt-client-tools.ts``).
    """
    slots = _CREATE_CLIENT_TOOL_SLOTS(dict(params or {}))
    return {
        "clientToolCallSlots": slots,
        "clientToolPolicy": _RESOLVE_CLIENT_TOOL_POLICY(dict(params or {})),
        "hasDeliveredSourceReply": bool(params.get("hasDeliveredSourceReply")),
    }


__all__ = [
    "EmbeddedAttemptClientTools",
    "prepare_embedded_attempt_client_tools",
    "set_create_client_tool_slots_hook",
    "set_resolve_client_tool_policy_hook",
]
