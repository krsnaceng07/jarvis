"""Gateway RPC handlers for agents operations — mirrors OpenClaw server-methods/agents.ts."""

from __future__ import annotations

import logging
from typing import Any

from jarvis_config_core import load_config

_log = logging.getLogger("jarvis.gateway.agents_handlers")


def agents_list_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle agents.list RPC request."""
    cfg = load_config()
    agents_roster = getattr(cfg, "agents", {})
    raw_list = agents_roster.get("list", []) if isinstance(agents_roster, dict) else []

    agents = []
    for a in raw_list:
        a_id = getattr(a, "id", "") or (a.get("id") if isinstance(a, dict) else "")
        a_name = getattr(a, "name", "") or (a.get("name") if isinstance(a, dict) else "")
        a_ws = getattr(a, "workspace", "") or (a.get("workspace") if isinstance(a, dict) else "")
        a_def = bool(getattr(a, "default", False) or (a.get("default") if isinstance(a, dict) else False))
        agents.append(
            {
                "id": a_id,
                "name": a_name,
                "workspace": a_ws,
                "default": a_def,
            }
        )

    if not agents:
        agents.append(
            {
                "id": "default",
                "name": "JARVIS Main Agent",
                "workspace": "",
                "default": True,
            }
        )

    return {
        "ok": True,
        "defaultAgentId": "default",
        "agents": agents,
    }


def make_agents_handlers() -> dict[str, Any]:
    """Return all agents-related gateway RPC handlers."""
    return {
        "agents.list": agents_list_handler,
    }


__all__ = ["make_agents_handlers"]
