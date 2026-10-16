"""jarvis.agents.agent_scope — higher-level agent scope helpers.

OpenClaw parity: mirrors ``src/agents/agent-scope.ts``.

This module is the stable public surface for agent scope resolution. It
re-exports everything from ``agent_scope_config`` and adds helpers that
combine routing session keys with workspace/dir resolution.

``src/routing/resolve_route.py`` imports ``resolve_default_agent_id`` from
``src.routing.agent_scope`` (which redirects here) — this module is the fix
for that broken import.
"""

from __future__ import annotations

from typing import Any

# Re-export the full agent_scope_config surface so callers only need one import.
from .agent_scope_config import (  # noqa: F401  (re-exports)
    DEFAULT_AGENT_ID,
    list_agent_entries,
    list_agent_ids,
    resolve_agent_config,
    resolve_agent_context_limits,
    resolve_agent_dir,
    resolve_agent_workspace_dir,
    resolve_default_agent_dir,
    resolve_default_agent_id,
)
from .agent_dir_registry import (  # noqa: F401  (re-exports)
    register_resolved_agent_dir,
    resolve_registered_agent_id_for_dir,
)
from .tool_catalog import GLOBAL_TOOL_CATALOG


# ---------------------------------------------------------------------------
# Session-key helpers
# ---------------------------------------------------------------------------


def resolve_agent_id_from_session_key(session_key: str) -> str | None:
    """Extract the agent id from an ``agent:<id>:…`` session key.

    Mirrors ``resolveAgentIdFromSessionKey``.

    Returns ``None`` for non-agent session keys.
    """
    if not isinstance(session_key, str) or not session_key.startswith("agent:"):
        return None
    tail = session_key[len("agent:"):]
    if not tail:
        return None
    agent_id = tail.split(":", 1)[0]
    if not agent_id:
        return None
    try:
        from src.routing.agent_id import normalize_agent_id  # noqa: PLC0415
        return normalize_agent_id(agent_id)
    except Exception:
        return None


def resolve_agent_workspace_dir_for_session(
    cfg: dict[str, Any],
    session_key: str,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the workspace dir for the agent that owns *session_key*.

    Mirrors ``resolveAgentWorkspaceDirForSession``.

    Falls back to the default agent's workspace when the session key
    cannot be parsed.
    """
    agent_id = resolve_agent_id_from_session_key(session_key)
    if agent_id:
        return resolve_agent_workspace_dir(cfg, agent_id, env)
    return resolve_agent_workspace_dir(cfg, resolve_default_agent_id(cfg), env)


def pick_first_existing_agent_id(cfg: dict[str, Any], agent_id: str) -> str:
    """Return *agent_id* if it is configured, else the default agent id.

    Mirrors ``pickFirstExistingAgentId``:
    - Looks up the entry; if present, returns the normalized id.
    - If absent, falls back to the default agent id.

    Used in ``resolve_route`` after a binding match so a binding that
    refers to a removed agent gracefully degrades to default.
    """
    from .agent_scope_config import (  # noqa: PLC0415
        _resolve_agent_entry,
        _normalize_agent_id,
    )
    try:
        nid = _normalize_agent_id(agent_id)
    except ValueError:
        return resolve_default_agent_id(cfg)

    entry = _resolve_agent_entry(cfg, nid)
    if entry is not None:
        return nid
    return resolve_default_agent_id(cfg)


def render_catalog_capability_directory(
    capability_tool_names: set[str],
) -> str | None:
    """Renders a compact catalog capability directory string for the system prompt.

    Mirrors OpenClaw's catalog injection, excluding parameter schemas to save tokens.
    """
    if not capability_tool_names:
        return None

    inventory = GLOBAL_TOOL_CATALOG.get_effective_inventory()
    
    # Filter and sort
    tools_to_render = [
        t for t in inventory if t.name in capability_tool_names
    ]
    if not tools_to_render:
        return None
        
    tools_to_render.sort(key=lambda t: t.name)

    lines = ["<tool_search_catalog>"]
    for t in tools_to_render:
        # Strip newlines from description to keep it compact
        desc = " ".join((t.description or "").split())
        lines.append(f"  - {t.name}: {desc}")
    lines.append("</tool_search_catalog>")
    
    return "\n".join(lines)


__all__ = [
    # Re-exports from agent_scope_config
    "DEFAULT_AGENT_ID",
    "list_agent_entries",
    "list_agent_ids",
    "resolve_agent_config",
    "resolve_agent_context_limits",
    "resolve_agent_dir",
    "resolve_agent_workspace_dir",
    "resolve_default_agent_dir",
    "resolve_default_agent_id",
    # Re-exports from agent_dir_registry
    "register_resolved_agent_dir",
    "resolve_registered_agent_id_for_dir",
    # Local helpers
    "resolve_agent_id_from_session_key",
    "resolve_agent_workspace_dir_for_session",
    "pick_first_existing_agent_id",
    "render_catalog_capability_directory",
]
