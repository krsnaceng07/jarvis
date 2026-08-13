"""Tool replay safety helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/tool-replay-safety.ts``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping, Optional


UNCONDITIONALLY_REPLAY_SAFE_TOOL_NAMES = frozenset(
    {
        "read",
        "search",
        "find",
        "grep",
        "glob",
        "ls",
        "web_search",
        "web_fetch",
        "x_search",
        "memory_get",
        "sessions_list",
        "sessions_history",
        "sessions_search",
        "agents_list",
        "conversations_list",
        "get_goal",
        "update_plan",
        "tool_search",
        "tool_describe",
        "image",
    }
)

TOOL_NAME_ALIASES = {
    "bash": "exec",
    "apply-patch": "apply_patch",
}

DeclaredReplaySafe = Callable[[Mapping[str, Any]], Optional[bool]]


def normalize_tool_name(name: Any) -> str:
    """Normalize a tool name to the policy id used for replay checks."""

    if not isinstance(name, str):
        return ""
    normalized = name.strip().lower()
    return TOOL_NAME_ALIASES.get(normalized, normalized)


def is_agent_tool_replay_safe(
    tool: Mapping[str, Any],
    *,
    declared_replay_safe: DeclaredReplaySafe | None = None,
) -> bool:
    """Return whether a concrete tool may be blindly replayed after retry.

    Owner declarations may only make an audited core name unsafe. They cannot
    make arbitrary extension-owned tools safe for blind replay.
    """

    if declared_replay_safe is not None and declared_replay_safe(tool) is False:
        return False
    return normalize_tool_name(tool.get("name")) in UNCONDITIONALLY_REPLAY_SAFE_TOOL_NAMES


def is_agent_tool_restart_safe(
    tool: Mapping[str, Any],
    *,
    declared_replay_safe: DeclaredReplaySafe | None = None,
) -> bool:
    """Return whether a concrete tool is safe for an explicitly restart-safe turn."""

    if declared_replay_safe is not None:
        declared = declared_replay_safe(tool)
        if declared is not None:
            return declared
    return normalize_tool_name(tool.get("name")) in UNCONDITIONALLY_REPLAY_SAFE_TOOL_NAMES


def collect_replay_safe_tool_names(
    tools: Iterable[Mapping[str, Any]],
    *,
    declared_replay_safe: DeclaredReplaySafe | None = None,
) -> set[str]:
    """Collect name-only replay-safe tool ids.

    Name-only metadata is accepted only when exactly one concrete registered
    tool owns the normalized name. Duplicate or shadowed names fail closed.
    """

    tools_by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for tool in tools:
        name = normalize_tool_name(tool.get("name"))
        if name:
            tools_by_name[name].append(tool)

    replay_safe_names: set[str] = set()
    for name, entries in tools_by_name.items():
        if len(entries) != 1:
            continue
        if is_agent_tool_replay_safe(
            entries[0],
            declared_replay_safe=declared_replay_safe,
        ):
            replay_safe_names.add(name)
    return replay_safe_names


__all__ = [
    "UNCONDITIONALLY_REPLAY_SAFE_TOOL_NAMES",
    "collect_replay_safe_tool_names",
    "is_agent_tool_replay_safe",
    "is_agent_tool_restart_safe",
    "normalize_tool_name",
]
