"""Gateway RPC handlers for tools operations — mirrors OpenClaw server-methods/tools-catalog.ts and tools-effective.ts."""

from __future__ import annotations

import logging
from typing import Any

from apps.desktop.src.jarvis_desktop.tool_declarations import TOOL_DECLARATIONS

_log = logging.getLogger("jarvis.gateway.tools_handlers")


def _build_core_tool_catalog() -> list[dict[str, Any]]:
    """Build the core tool catalog entries grouped by category."""
    core_tools: list[dict[str, Any]] = []
    coding_tools: list[dict[str, Any]] = []

    for decl in TOOL_DECLARATIONS:
        name = decl.get("name", "")
        desc = decl.get("description", "")
        entry = {
            "id": name,
            "label": name.replace("_", " ").title(),
            "description": desc,
            "source": "core",
            "defaultProfiles": ["full"],
        }
        if name in {"bash", "file_edit", "codebase_search"}:
            entry["defaultProfiles"].append("coding")
            coding_tools.append(entry)
        else:
            core_tools.append(entry)

    groups = [
        {
            "id": "core",
            "label": "Core System Tools",
            "source": "core",
            "tools": core_tools,
        },
        {
            "id": "coding",
            "label": "Coding Tools",
            "source": "core",
            "tools": coding_tools,
        },
    ]
    return groups


def tools_catalog_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle tools.catalog RPC request."""
    groups = _build_core_tool_catalog()
    return {
        "ok": True,
        "groups": groups,
    }


def tools_effective_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle tools.effective RPC request."""
    agent_id = params.get("agentId") or "default"
    session_id = params.get("sessionId")
    tools = [dict(t) for t in TOOL_DECLARATIONS]
    return {
        "ok": True,
        "agentId": agent_id,
        "sessionId": session_id,
        "tools": tools,
    }


def make_tools_handlers() -> dict[str, Any]:
    """Return all tools-related gateway RPC handlers."""
    return {
        "tools.catalog": tools_catalog_handler,
        "tools.effective": tools_effective_handler,
    }


__all__ = ["make_tools_handlers"]
