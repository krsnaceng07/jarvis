"""OpenClaw-owned dynamic tool projection for Codex turns."""

from __future__ import annotations

import re
from typing import Any, Iterable

OPENCLAW_NAMESPACE = "openclaw"
OPENCLAW_DIRECT_NAMESPACE = "openclaw_direct"
DEFAULT_CODEX_DYNAMIC_TOOL_EXCLUDE = frozenset(
    {
        "read",
        "write",
        "edit",
        "apply_patch",
        "exec",
        "process",
        "get_goal",
        "create_goal",
        "update_goal",
        "tool_call",
        "tool_describe",
        "tool_search",
        "tool_search_code",
    }
)
ALWAYS_DIRECT_DYNAMIC_TOOL_NAMES = frozenset(
    {"agents_list", "agents_wait", "progress_card", "sessions_spawn", "sessions_yield"}
)
_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def project_codex_dynamic_tools(
    tools: Iterable[dict[str, Any]],
    *,
    loading: str = "searchable",
    exclude: Iterable[str] = (),
    direct_names: Iterable[str] = (),
) -> dict[str, Any]:
    """Project OpenClaw tools into Codex direct and searchable namespaces."""
    excluded = DEFAULT_CODEX_DYNAMIC_TOOL_EXCLUDE | {str(name) for name in exclude}
    direct = ALWAYS_DIRECT_DYNAMIC_TOOL_NAMES | {str(name) for name in direct_names}
    entries: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for index, tool in enumerate(tools):
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or not name:
            quarantined.append({"tool": f"tool[{index}]", "violations": ["name is required"]})
            continue
        if name in excluded:
            continue
        if name == "mcp" or name.startswith("mcp__"):
            quarantined.append({"tool": name, "violations": ["name is reserved by Codex"]})
            continue
        if name.strip() != name or not _TOOL_NAME_PATTERN.fullmatch(name) or len(name) > 128:
            quarantined.append({"tool": name, "violations": ["invalid Codex tool name"]})
            continue
        schema = tool.get("inputSchema", tool.get("parameters", {}))
        if not isinstance(schema, dict):
            quarantined.append({"tool": name, "violations": ["inputSchema must be an object"]})
            continue
        entries.append(
            {
                "name": name,
                "description": str(tool.get("description") or ""),
                "inputSchema": schema,
                "catalogMode": tool.get("catalogMode"),
            }
        )

    projected: list[dict[str, Any]] = []
    searchable: list[dict[str, Any]] = []
    direct_only: list[dict[str, Any]] = []
    ordered = entries if loading == "direct" else sorted(entries, key=lambda item: item["name"])
    for entry in ordered:
        spec = {key: value for key, value in entry.items() if key != "catalogMode"}
        if entry["catalogMode"] == "direct-only":
            direct_only.append(spec)
        elif loading == "direct" or entry["name"] in direct:
            projected.append(spec)
        else:
            searchable.append({**spec, "deferLoading": True})
    if searchable:
        projected.append({"type": "namespace", "name": OPENCLAW_NAMESPACE, "tools": searchable})
    if direct_only:
        projected.append(
            {"type": "namespace", "name": OPENCLAW_DIRECT_NAMESPACE, "tools": direct_only}
        )
    return {"specs": projected, "quarantined": quarantined}


__all__ = [
    "ALWAYS_DIRECT_DYNAMIC_TOOL_NAMES",
    "DEFAULT_CODEX_DYNAMIC_TOOL_EXCLUDE",
    "OPENCLAW_DIRECT_NAMESPACE",
    "OPENCLAW_NAMESPACE",
    "project_codex_dynamic_tools",
]
