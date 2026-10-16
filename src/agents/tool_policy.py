"""jarvis.agents.tool_policy — tool allow/deny policy matching, profiles, and group expansion.

OpenClaw parity: mirrors
``openclaw-main/src/agents/tool-policy.ts``,
``openclaw-main/src/agents/tool-policy-shared.ts``,
``openclaw-main/src/agents/tool-catalog.ts``, and
``openclaw-main/src/agents/agent-tools.policy.ts``.

Features:
- Tool name normalization (e.g. `bash` -> `exec`, `apply-patch` -> `apply_patch`).
- Built-in Profiles: "minimal", "coding", "messaging", "full".
- Subagent tool restriction lists: `SUBAGENT_TOOL_DENY_ALWAYS` and `SUBAGENT_TOOL_DENY_LEAF`.
- Group expansion (`group:fs`, `group:runtime`, `group:web`, `group:memory`, `group:sessions`).
- Wildcard pattern matching (`*`, `read*`, `browser*`, etc.).
- Deny patterns take precedence over allow patterns.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence

from .tool_search import TOOL_SEARCH_CONTROL_TOOL_NAMES

ToolProfileId = Literal["minimal", "coding", "messaging", "full"]

# ---------------------------------------------------------------------------
# Aliases, Profiles and Groups
# ---------------------------------------------------------------------------

TOOL_NAME_ALIASES: dict[str, str] = {
    "bash": "exec",
    "apply-patch": "apply_patch",
}

CORE_TOOL_GROUPS: dict[str, list[str]] = {
    "group:fs": ["read", "write", "edit", "apply_patch"],
    "group:runtime": ["exec", "process"],
    "group:web": ["browser", "canvas", "web_search", "web_fetch"],
    "group:memory": ["memory_search", "memory_get"],
    "group:sessions": [
        "sessions_list",
        "sessions_history",
        "sessions_search",
        "sessions_send",
        "sessions_spawn",
        "session_status",
    ],
    # Shortcuts without "group:" prefix
    "fs": ["read", "write", "edit", "apply_patch"],
    "runtime": ["exec", "process"],
    "web": ["browser", "canvas", "web_search", "web_fetch"],
    "memory": ["memory_search", "memory_get"],
    "sessions": [
        "sessions_list",
        "sessions_history",
        "sessions_search",
        "sessions_send",
        "sessions_spawn",
        "session_status",
    ],
}

PROFILE_ALLOW_MAP: dict[ToolProfileId, list[str]] = {
    "minimal": ["session_status", "ask_user"],
    "coding": [
        "read",
        "write",
        "edit",
        "apply_patch",
        "exec",
        "process",
        "code_execution",
        "web_search",
        "web_fetch",
        "x_search",
        "memory_search",
        "memory_get",
        "sessions",
        "sessions_list",
        "sessions_history",
        "sessions_search",
        "sessions_send",
        "sessions_spawn",
        "agents_wait",
        "sessions_yield",
        "subagents",
        "session_status",
        "spawn_task",
        "dismiss_task",
        "screen",
        "dashboard",
        "terminal",
        "cron",
        "get_goal",
        "create_goal",
        "update_goal",
        "ask_user",
        "view_image",
        "show_widget",
    ],
    "messaging": [
        "sessions",
        "sessions_list",
        "sessions_history",
        "sessions_search",
        "conversations_list",
        "conversations_send",
        "conversations_turn",
        "sessions_send",
        "sessions_spawn",
        "sessions_yield",
        "subagents",
        "session_status",
        "message",
        "ask_user",
    ],
    "full": ["*"],
}

SUBAGENT_TOOL_DENY_ALWAYS: list[str] = [
    "gateway",
    "agents_list",
    "session_status",
    "cron",
    "sessions_send",
    "conversations_list",
    "conversations_send",
    "conversations_turn",
]

SUBAGENT_TOOL_DENY_LEAF: list[str] = [
    "subagents",
    "sessions_list",
    "sessions_history",
    "sessions_search",
    "sessions_spawn",
]


def resolve_subagent_deny_list(role: Literal["leaf", "orchestrator"] = "leaf") -> list[str]:
    """Resolve denied tools for a subagent based on its role."""
    if role == "leaf":
        return list(set(SUBAGENT_TOOL_DENY_ALWAYS + SUBAGENT_TOOL_DENY_LEAF))
    return list(SUBAGENT_TOOL_DENY_ALWAYS)


def resolve_tool_profile_policy(profile: ToolProfileId) -> dict[str, list[str]]:
    """Resolve allow policy array for a given tool profile."""
    allow = PROFILE_ALLOW_MAP.get(profile, ["*"])
    return {"allow": list(allow)}


def normalize_tool_name(name: str) -> str:
    """Normalize a tool name or alias to the policy ID used for matching."""
    if not isinstance(name, str):
        return ""
    normalized = name.strip().lower()
    return TOOL_NAME_ALIASES.get(normalized, normalized)


def expand_tool_groups(tool_list: Sequence[str] | None) -> list[str]:
    """Expand named tool groups into concrete tool IDs."""
    if not tool_list:
        return []

    expanded: list[str] = []
    seen: set[str] = set()

    for item in tool_list:
        if not isinstance(item, str):
            continue
        normalized = normalize_tool_name(item)
        if not normalized:
            continue
        if normalized in CORE_TOOL_GROUPS:
            for g_item in CORE_TOOL_GROUPS[normalized]:
                if g_item not in seen:
                    seen.add(g_item)
                    expanded.append(g_item)
        else:
            if normalized not in seen:
                seen.add(normalized)
                expanded.append(normalized)

    return expanded


def match_pattern(tool_name: str, pattern: str) -> bool:
    """Match a tool name against a single policy pattern (supports wildcards)."""
    norm_tool = normalize_tool_name(tool_name)
    norm_pat = normalize_tool_name(pattern)

    if norm_pat == "*":
        return True

    if norm_tool == norm_pat:
        return True

    # Wildcard fnmatch
    if "*" in norm_pat or "?" in norm_pat:
        if fnmatch.fnmatch(norm_tool, norm_pat):
            return True

    # Special case: 'write' pattern allows 'apply_patch'
    if norm_pat == "write" and norm_tool == "apply_patch":
        return True

    return False


def is_tool_allowed_by_policy(
    tool_name: str,
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
) -> bool:
    """Check if *tool_name* is allowed under the given allow/deny rules."""
    norm_tool = normalize_tool_name(tool_name)
    if not norm_tool:
        return False

    expanded_deny = expand_tool_groups(deny)
    for pattern in expanded_deny:
        if match_pattern(norm_tool, pattern):
            return False

    expanded_allow = expand_tool_groups(allow)
    if not expanded_allow:
        return True

    for pattern in expanded_allow:
        if match_pattern(norm_tool, pattern):
            return True

    return False


def filter_tools_by_policy(
    tools: Sequence[Any],
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    name_getter: Callable[[Any], str] | None = None,
) -> list[Any]:
    """Filter a sequence of tool definitions or names using allow/deny policy."""
    filtered: list[Any] = []
    for item in tools:
        if name_getter:
            t_name = name_getter(item)
        elif isinstance(item, str):
            t_name = item
        elif isinstance(item, dict) and "name" in item:
            t_name = item["name"]
        elif hasattr(item, "name"):
            t_name = getattr(item, "name")
        else:
            t_name = str(item)

        if is_tool_allowed_by_policy(t_name, allow=allow, deny=deny):
            filtered.append(item)

    return filtered


@dataclass
class ToolSearchRunPlan:
    visible_allowed_tool_names: set[str]
    replay_allowed_tool_names: set[str]
    live_allowed_tool_names: set[str]
    capability_tool_names: set[str]
    empty_allowlist_callable_names: list[str]


def build_tool_search_run_plan(
    visible_tools: Sequence[Any],
    uncompacted_tools: Sequence[Any],
    controls_enabled: bool,
    deferred_tools_callable: bool = False,
    control_names: Sequence[str] | None = None,
    catalog_tool_count: int = 0,
    name_getter: Callable[[Any], str] | None = None,
) -> ToolSearchRunPlan:
    """Builds the complete tool-search allowlist plan for one run."""

    def get_names(tools_seq: Sequence[Any]) -> set[str]:
        names = set()
        for item in tools_seq:
            if name_getter:
                names.add(normalize_tool_name(name_getter(item)))
            elif hasattr(item, "name"):
                names.add(normalize_tool_name(getattr(item, "name")))
            elif isinstance(item, dict) and "name" in item:
                names.add(normalize_tool_name(item["name"]))
            elif isinstance(item, str):
                names.add(normalize_tool_name(item))
        return {n for n in names if n}

    visible_allowed = get_names(visible_tools)
    replay_allowed = get_names(uncompacted_tools)
    capability_names = get_names(uncompacted_tools if deferred_tools_callable else visible_tools)

    ctrl_names = set(control_names or TOOL_SEARCH_CONTROL_TOOL_NAMES)

    if controls_enabled:
        for ctrl in ctrl_names:
            if ctrl in visible_allowed:
                replay_allowed.add(ctrl)

    live_allowed = (
        set(get_names(uncompacted_tools)) if deferred_tools_callable else set(visible_allowed)
    )

    if deferred_tools_callable:
        for ctrl in ctrl_names:
            if ctrl not in visible_allowed:
                live_allowed.discard(ctrl)
                capability_names.discard(ctrl)
        live_allowed.update(visible_allowed)

    empty_callable = [
        name
        for name in (get_names(visible_tools) if deferred_tools_callable else visible_allowed)
        if name not in ctrl_names
    ]

    return ToolSearchRunPlan(
        visible_allowed_tool_names=visible_allowed,
        replay_allowed_tool_names=replay_allowed,
        live_allowed_tool_names=live_allowed,
        capability_tool_names=capability_names,
        empty_allowlist_callable_names=empty_callable,
    )


__all__ = [
    "CORE_TOOL_GROUPS",
    "PROFILE_ALLOW_MAP",
    "SUBAGENT_TOOL_DENY_ALWAYS",
    "SUBAGENT_TOOL_DENY_LEAF",
    "TOOL_NAME_ALIASES",
    "ToolProfileId",
    "expand_tool_groups",
    "filter_tools_by_policy",
    "is_tool_allowed_by_policy",
    "match_pattern",
    "normalize_tool_name",
    "resolve_subagent_deny_list",
    "resolve_tool_profile_policy",
    "ToolSearchRunPlan",
    "build_tool_search_run_plan",
]
