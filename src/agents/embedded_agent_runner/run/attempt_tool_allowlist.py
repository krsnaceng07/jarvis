"""jarvis.agents.embedded_agent_runner.run.attempt_tool_allowlist — collect explicit tool-allowlist sources for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-tool-allowlist.ts``.

Public surface:

- :func:`collect_attempt_explicit_tool_allowlist_sources`

Phase 7.6d-1 — focused minimal port.

The OpenClaw source is small and pulls tool-policy fields from the
attempt's resolved capability profile. The Python port keeps the
public surface and delegates the heavy list-merge to an
installable hook so the host can plug in the real
``collectExplicitToolAllowlistSources`` helper as it lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List


#: Tool-allowlist source shape.
ToolAllowlistSource = Dict[str, Any]


#: Allowlist-collect result shape.
ToolAllowlistCollectResult = Dict[str, Any]


#: Resolved conversation capability profile.
ResolvedConversationCapabilityProfile = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`collectExplicitToolAllowlistSources` from
#: ``tool-allowlist-guard.ts``.
_COLLECT_EXPLICIT_TOOL_ALLOWLIST_SOURCES: Callable[
    [List[Dict[str, Any]]], ToolAllowlistCollectResult
] = lambda _sources: {"sources": []}


def set_collect_explicit_tool_allowlist_sources_hook(
    hook: Callable[[List[Dict[str, Any]]], ToolAllowlistCollectResult],
) -> None:
    """Install a custom collectExplicitToolAllowlistSources hook."""
    global _COLLECT_EXPLICIT_TOOL_ALLOWLIST_SOURCES
    _COLLECT_EXPLICIT_TOOL_ALLOWLIST_SOURCES = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_attempt_explicit_tool_allowlist_sources(
    params: Dict[str, Any],
) -> ToolAllowlistCollectResult:
    """Collect the explicit tool-allowlist sources for one attempt.

    Mirrors :func:`collectAttemptExplicitToolAllowlistSources`
    (``attempt-tool-allowlist.ts:4-39``).
    """
    capability_profile = params.get("capabilityProfile") or {}
    tools_allow = params.get("toolsAllow")
    policy = capability_profile.get("policy") or {}
    agent_id = capability_profile.get("agentId")
    sources: List[Dict[str, Any]] = [
        {"label": "tools.allow", "allow": policy.get("globalPolicy", {}).get("allow")},
        {
            "label": "tools.byProvider.allow",
            "allow": policy.get("globalProviderPolicy", {}).get("allow"),
        },
        {
            "label": (
                f"agents.{agent_id}.tools.allow" if agent_id else "agent tools.allow"
            ),
            "allow": policy.get("agentPolicy", {}).get("allow"),
        },
        {
            "label": (
                f"agents.{agent_id}.tools.byProvider.allow"
                if agent_id
                else "agent tools.byProvider.allow"
            ),
            "allow": policy.get("agentProviderPolicy", {}).get("allow"),
        },
        {"label": "group tools.allow", "allow": policy.get("groupPolicy", {}).get("allow")},
        {
            "label": "sandbox tools.allow",
            "allow": policy.get("sandboxPolicy", {}).get("allow"),
        },
        {
            "label": "subagent tools.allow",
            "allow": policy.get("subagentPolicy", {}).get("allow"),
        },
        {
            "label": "inherited tools.allow",
            "allow": policy.get("inheritedToolPolicy", {}).get("allow"),
        },
        {
            "label": "runtime toolsAllow",
            "allow": tools_allow,
            "enforceWhenToolsDisabled": True,
        },
    ]
    return _COLLECT_EXPLICIT_TOOL_ALLOWLIST_SOURCES(sources)


__all__ = [
    "ResolvedConversationCapabilityProfile",
    "ToolAllowlistCollectResult",
    "ToolAllowlistSource",
    "collect_attempt_explicit_tool_allowlist_sources",
    "set_collect_explicit_tool_allowlist_sources_hook",
]
