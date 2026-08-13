"""Tool schema projection & quarantine — mirrors OpenClaw ``src/agents/tool-schema-projection.ts``."""

from __future__ import annotations

from typing import Any
from .tool_catalog import GLOBAL_TOOL_CATALOG, ToolDescriptor


def project_tool_schema(tool: ToolDescriptor, max_description_len: int = 200) -> dict[str, Any]:
    """Trim tool schema for token optimization before injecting into LLM context."""
    desc = tool.description
    if len(desc) > max_description_len:
        desc = desc[: max_description_len - 3] + "..."

    return {
        "name": tool.name,
        "description": desc,
        "parameters": tool.parameters_schema or {"type": "object", "properties": {}},
    }


def quarantine_tool(tool_name: str, reason: str) -> bool:
    """Quarantine a tool so it is excluded from effective inventory."""
    return GLOBAL_TOOL_CATALOG.quarantine(tool_name, reason)


__all__ = ["project_tool_schema", "quarantine_tool"]
