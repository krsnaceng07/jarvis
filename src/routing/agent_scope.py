"""jarvis.routing.agent_scope — configured-agent id resolution (routing subset).

OpenClaw parity: mirrors the id-resolution subset of
``src/agents/agent-scope-config.ts`` (``listAgentEntries``,
``listAgentIds``, ``resolveDefaultAgentId``). Directory/workspace
resolution stays in the existing jarvis_sdk agent_runtime module; the
routing tiers only need id lookup semantics.
"""

from __future__ import annotations

import sys
from typing import Any

from .agent_id import DEFAULT_AGENT_ID, normalize_agent_id

_default_agent_warned = False


def _warn_multiple_default_agents() -> None:
    print(
        "[agent-scope] Multiple agents marked default=true; using the first entry as default.",
        file=sys.stderr,
    )


def reset_default_agent_warning_for_tests() -> None:
    global _default_agent_warned
    _default_agent_warned = False


def list_agent_entries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """List valid configured agent entries from config."""
    agents = cfg.get("agents")
    agent_list = agents.get("list") if isinstance(agents, dict) else None
    if not isinstance(agent_list, list):
        return []
    return [entry for entry in agent_list if entry is not None and isinstance(entry, dict)]


def list_agent_ids(cfg: dict[str, Any]) -> list[str]:
    """List unique configured agent ids, falling back to the default agent id."""
    agents = list_agent_entries(cfg)
    if not agents:
        return [DEFAULT_AGENT_ID]
    seen: set[str] = set()
    ids: list[str] = []
    for entry in agents:
        agent_id = normalize_agent_id(entry.get("id"))
        if agent_id in seen:
            continue
        seen.add(agent_id)
        ids.append(agent_id)
    return ids if ids else [DEFAULT_AGENT_ID]


def resolve_default_agent_id(cfg: dict[str, Any]) -> str:
    """Resolve the default agent id, warning once when multiple defaults exist."""
    global _default_agent_warned
    agents = list_agent_entries(cfg)
    if not agents:
        return DEFAULT_AGENT_ID
    defaults = [agent for agent in agents if agent.get("default")]
    if len(defaults) > 1 and not _default_agent_warned:
        _default_agent_warned = True
        _warn_multiple_default_agents()
    chosen_entry = defaults[0] if defaults else agents[0]
    chosen_raw = chosen_entry.get("id")
    chosen = chosen_raw.strip() if isinstance(chosen_raw, str) else ""
    return normalize_agent_id(chosen or DEFAULT_AGENT_ID)


__all__ = [
    "list_agent_entries",
    "list_agent_ids",
    "reset_default_agent_warning_for_tests",
    "resolve_default_agent_id",
]
