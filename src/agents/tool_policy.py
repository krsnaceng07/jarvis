"""Tool policy pipeline — mirrors OpenClaw ``src/agents/agent-tools.policy.ts``.

Supports tool group expansion, exclusions, allow/deny lists, and canonical normalization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

_log = logging.getLogger("jarvis.agents.tool_policy")

# Predefined tool groups (mirrors OpenClaw DEFAULT_TOOL_GROUPS)
DEFAULT_TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "group:read": ("read_file", "view_file", "list_dir", "grep_search", "find_by_name"),
    "group:write": ("write_to_file", "replace_file_content", "multi_replace_file_content"),
    "group:exec": ("bash", "run_command"),
    "group:web": ("search_web", "read_url_content", "browser_subagent"),
    "group:memory": ("memory_search", "memory_get", "memory_set"),
    "group:coding": ("read_file", "view_file", "write_to_file", "replace_file_content", "grep_search", "bash"),
}


def expand_tool_groups(declared: Sequence[str]) -> list[str]:
    """Expand group labels (e.g. 'group:coding') and wildcard '*' into concrete tool names."""
    expanded: set[str] = set()
    exclusions: set[str] = set()

    for item in declared:
        item_str = item.strip()
        if not item_str:
            continue
        if item_str.startswith("!"):
            exclusions.add(item_str[1:].strip())
        elif item_str in DEFAULT_TOOL_GROUPS:
            expanded.update(DEFAULT_TOOL_GROUPS[item_str])
        else:
            expanded.add(item_str)

    # Filter out exclusions
    result = [t for t in expanded if t not in exclusions and t != "*"]
    return sorted(set(result))


def normalize_tool_list(tools: Sequence[str]) -> list[str]:
    """Return canonical, deduplicated, sorted list of tool names."""
    cleaned = set()
    for t in tools:
        t_str = t.strip()
        if t_str and not t_str.startswith("!"):
            cleaned.add(t_str)
    return sorted(cleaned)


def apply_tool_policy_pipeline(
    available_tools: Sequence[str],
    config_allowlist: Sequence[str] | None = None,
    config_denylist: Sequence[str] | None = None,
    plugin_allowlist: Sequence[str] | None = None,
) -> list[str]:
    """Compute effective allowed tools given available, config allow/deny, and plugin rules."""
    effective = set(available_tools)

    # Apply plugin allowlist if present
    if plugin_allowlist is not None and len(plugin_allowlist) > 0:
        expanded_plugin = set(expand_tool_groups(plugin_allowlist))
        effective = effective.intersection(expanded_plugin)

    # Apply config allowlist if present
    if config_allowlist is not None and len(config_allowlist) > 0:
        expanded_config = set(expand_tool_groups(config_allowlist))
        effective = effective.intersection(expanded_config)

    # Apply config denylist if present
    if config_denylist is not None and len(config_denylist) > 0:
        expanded_deny = set(expand_tool_groups(config_denylist))
        effective = effective.difference(expanded_deny)

    return sorted(effective)


__all__ = [
    "DEFAULT_TOOL_GROUPS",
    "apply_tool_policy_pipeline",
    "expand_tool_groups",
    "normalize_tool_list",
]
