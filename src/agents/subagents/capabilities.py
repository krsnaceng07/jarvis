"""src.agents.subagents.capabilities
Subagent capability resolution, depth tracking, and tool access scoping.

Matches OpenClaw parity:
- src/agents/subagents/spawn/subagent-capabilities.ts
- src/agents/subagents/spawn/subagent-depth.ts
- src/agents/subagents/inherited-tool-deny.ts
"""

from __future__ import annotations

from typing import Any

from .types import SubagentRole

DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH: int = 3

# Built-in tools that control or spawn subagents
SUBAGENT_DELEGATION_TOOLS: frozenset[str] = frozenset(
    {
        "sessions_spawn",
        "sessions_yield",
    }
)

# Tools denied for leaf subagents to enforce one-way delegation
LEAF_DENIED_TOOLS: frozenset[str] = frozenset(
    {
        "sessions_spawn",
        "sessions_yield",
        "shutdown",
        "desktop_shutdown",
    }
)

# Safe tools commonly permitted for leaf execution
DEFAULT_LEAF_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "read",
        "write",
        "edit",
        "ls",
        "exec",
        "process",
        "mkdir",
        "remove_path",
        "rename_path",
        "open_path",
        "browser",
        "web_search",
        "subagents",  # Can list or check status of its own tasks
    }
)


def resolve_subagent_role(
    depth: int, max_spawn_depth: int = DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH
) -> SubagentRole:
    """Resolve role for a given depth level.

    depth <= 0: main agent
    0 < depth < max_spawn_depth: orchestrator
    depth >= max_spawn_depth: leaf
    """
    if depth <= 0:
        return SubagentRole.MAIN
    if depth < max_spawn_depth:
        return SubagentRole.ORCHESTRATOR
    return SubagentRole.LEAF


def can_spawn_subagents(
    role: SubagentRole, depth: int, max_spawn_depth: int = DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH
) -> bool:
    """Check if an agent with the given role and depth is authorized to spawn children."""
    if depth >= max_spawn_depth:
        return False
    return role in (SubagentRole.MAIN, SubagentRole.ORCHESTRATOR)


def can_control_children(role: SubagentRole) -> bool:
    """Check if an agent has child control scope."""
    return role != SubagentRole.LEAF


def filter_tools_for_subagent(
    role: SubagentRole,
    tools: dict[str, Any],
    inherited_allow: list[str] | set[str] | None = None,
    inherited_deny: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Filter available tools according to the subagent's role and policy envelopes."""
    filtered: dict[str, Any] = {}
    allow_set = set(inherited_allow) if inherited_allow else None
    deny_set = set(inherited_deny) if inherited_deny else set()

    for name, tool in tools.items():
        # 1. Deny rules specific to leaf role
        if role == SubagentRole.LEAF and name in LEAF_DENIED_TOOLS:
            continue

        # 2. Explicit inherited deny
        if name in deny_set:
            continue

        # 3. Explicit inherited allow (if specified, only allowed tools pass)
        if allow_set is not None and name not in allow_set:
            continue

        filtered[name] = tool

    return filtered
