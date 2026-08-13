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

__all__ = ["GLOBAL_TOOL_CATALOG", "ToolCatalog", "ToolDescriptor"]
