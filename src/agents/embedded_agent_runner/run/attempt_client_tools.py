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

from typing import Any, Callable, Dict, List, Mapping

from src.agents.embedded_agent_runner.tool_name_allowlist import (
    collect_registered_tool_names,
    to_session_tool_allowlist,
)
from src.agents.embedded_agent_runner.tool_split import split_sdk_tools
from src.agents.tool_replay_safety import (
    collect_replay_safe_tool_names,
    is_agent_tool_replay_safe,
)


#: Embedded-attempt client-tools shape.
EmbeddedAttemptClientTools = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def _default_resolve_client_tool_policy(_params: Dict[str, Any]) -> Any:
    return None


#: Hook for the resolve-client-tool-policy step.
_RESOLVE_CLIENT_TOOL_POLICY: Callable[[Dict[str, Any]], Any] = (
    _default_resolve_client_tool_policy
)


def set_resolve_client_tool_policy_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolve-client-tool-policy hook."""
    global _RESOLVE_CLIENT_TOOL_POLICY
    _RESOLVE_CLIENT_TOOL_POLICY = hook


def _default_create_client_tool_slots(
    _params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return []


#: Hook for the create-client-tool-slots step.
_CREATE_CLIENT_TOOL_SLOTS: Callable[[Dict[str, Any]], List[Dict[str, Any]]] = (
    _default_create_client_tool_slots
)


def set_create_client_tool_slots_hook(
    hook: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
) -> None:
    """Install a custom create-client-tool-slots hook."""
    global _CREATE_CLIENT_TOOL_SLOTS
    _CREATE_CLIENT_TOOL_SLOTS = hook


def _tool_name(tool: Any) -> str:
    value = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
    return value.strip() if isinstance(value, str) else ""


def _is_plugin_tool(tool: Any) -> bool:
    if isinstance(tool, dict):
        return bool(tool.get("plugin") or tool.get("pluginId") or tool.get("pluginMeta"))
    return bool(
        getattr(tool, "plugin", None)
        or getattr(tool, "pluginId", None)
        or getattr(tool, "pluginMeta", None)
    )


def _declared_replay_safe(
    options: Mapping[str, Any] | None,
    tool: Mapping[str, Any],
) -> bool | None:
    if not options:
        return None
    declared = options.get("declaredReplaySafe") or options.get("declared_replay_safe")
    if callable(declared):
        return declared(tool)
    return None


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
    params = dict(params or {})
    effective_tools = list(params.get("effectiveTools") or [])
    uncompacted_effective_tools = list(
        params.get("uncompactedEffectiveTools") or effective_tools
    )
    split = split_sdk_tools(
        {
            "tools": effective_tools,
            "sandboxEnabled": bool(params.get("sandboxEnabled")),
            "toolHookContext": params.get("catalogToolHookContext"),
        }
    )
    custom_tools = list(split.get("customTools") or [])
    client_tool_defs = list(params.get("clientTools") or [])
    slots = _CREATE_CLIENT_TOOL_SLOTS(params)
    replay_safety_options = params.get("replaySafetyOptions")

    replay_safe_tools = [
        tool
        for tool in uncompacted_effective_tools
        if is_agent_tool_replay_safe(
            {"name": _tool_name(tool)},
            declared_replay_safe=lambda _candidate, source=tool: _declared_replay_safe(
                replay_safety_options if isinstance(replay_safety_options, Mapping) else None,
                {"name": _tool_name(source)},
            ),
        )
    ]
    replay_safe_tool_names = collect_replay_safe_tool_names(
        [{"name": _tool_name(tool)} for tool in uncompacted_effective_tools],
        declared_replay_safe=(
            (lambda tool: _declared_replay_safe(replay_safety_options, tool))
            if isinstance(replay_safety_options, Mapping)
            else None
        ),
    )
    all_custom_tools = [*custom_tools, *client_tool_defs]
    return {
        "allCustomTools": all_custom_tools,
        "builtinToolNames": {
            name
            for name in (_tool_name(tool) for tool in uncompacted_effective_tools)
            if name
        },
        "clientToolCallSlots": slots,
        "clientToolDefs": client_tool_defs,
        "clientToolLoopDetection": None,
        "replaySafeToolNames": replay_safe_tool_names,
        "replaySafeTools": replay_safe_tools,
        "sessionToolAllowlist": to_session_tool_allowlist(
            collect_registered_tool_names(all_custom_tools)
        ),
        # Legacy Python hook fields kept until callers switch to the OpenClaw
        # result shape above.
        "clientToolPolicy": _RESOLVE_CLIENT_TOOL_POLICY(dict(params or {})),
        "hasDeliveredSourceReply": bool(params.get("hasDeliveredSourceReply")),
    }


__all__ = [
    "EmbeddedAttemptClientTools",
    "prepare_embedded_attempt_client_tools",
    "set_create_client_tool_slots_hook",
    "set_resolve_client_tool_policy_hook",
]
