"""Tool catalog inventory — mirrors OpenClaw ``src/agents/tool-catalog.ts``."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("jarvis.agents.tool_catalog")


@dataclass
class ToolDescriptor:
    name: str
    description: str
    source: str = "core"       # "core" | "plugin" | "mcp"
    plugin_id: str | None = None
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    quarantined: bool = False
    quarantine_reason: str | None = None


class ToolCatalog:
    """Registry of all available tools across core, plugin, and MCP sources."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, desc: ToolDescriptor) -> None:
        self._tools[desc.name] = desc
        _log.debug("Registered tool in catalog: %s (source=%s)", desc.name, desc.source)

    def get(self, name: str) -> ToolDescriptor | None:
        return self._tools.get(name)

    def list_all(self) -> list[ToolDescriptor]:
        return list(self._tools.values())

    def get_effective_inventory(self, include_quarantined: bool = False) -> list[ToolDescriptor]:
        if include_quarantined:
            return self.list_all()
        return [t for t in self._tools.values() if not t.quarantined]

    def quarantine(self, name: str, reason: str) -> bool:
        tool = self._tools.get(name)
        if not tool:
            return False
        tool.quarantined = True
        tool.quarantine_reason = reason
        _log.warning("Quarantined tool '%s': %s", name, reason)
        return True


GLOBAL_TOOL_CATALOG = ToolCatalog()

# Register core session tools
try:
    from .sessions.tools import (
        create_sessions_list_tool_definition,
        create_session_status_tool_definition,
        create_sessions_send_tool_definition,
    )
    list_def = create_sessions_list_tool_definition()
    GLOBAL_TOOL_CATALOG.register(ToolDescriptor(
        name=list_def["name"],
        description=list_def["description"],
        source="core",
        parameters_schema=list_def.get("inputSchema", {})
    ))

    status_def = create_session_status_tool_definition()
    GLOBAL_TOOL_CATALOG.register(ToolDescriptor(
        name=status_def["name"],
        description=status_def["description"],
        source="core",
        parameters_schema=status_def.get("inputSchema", {})
    ))

    send_def = create_sessions_send_tool_definition()
    GLOBAL_TOOL_CATALOG.register(ToolDescriptor(
        name=send_def["name"],
        description=send_def["description"],
        source="core",
        parameters_schema=send_def.get("inputSchema", {})
    ))

    # Import and register the new session tools
    from .sessions.tools import (
        create_sessions_tool_definition,
        create_sessions_search_tool_definition,
        create_sessions_history_tool_definition,
        create_conversations_list_tool_definition,
        create_conversations_send_tool_definition,
        create_conversations_turn_tool_definition,
        create_sessions_spawn_tool_definition,
        create_sessions_yield_tool_definition,
        create_subagents_tool_definition,
    )
    
    for factory in [
        create_sessions_tool_definition,
        create_sessions_search_tool_definition,
        create_sessions_history_tool_definition,
        create_conversations_list_tool_definition,
        create_conversations_send_tool_definition,
        create_conversations_turn_tool_definition,
        create_sessions_spawn_tool_definition,
        create_sessions_yield_tool_definition,
        create_subagents_tool_definition,
    ]:
        td_def = factory()
        GLOBAL_TOOL_CATALOG.register(ToolDescriptor(
            name=td_def["name"],
            description=td_def["description"],
            source="core",
            parameters_schema=td_def.get("inputSchema", {})
        ))
except ImportError:
    pass

__all__ = ["GLOBAL_TOOL_CATALOG", "ToolCatalog", "ToolDescriptor"]
