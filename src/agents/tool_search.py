"""Tool search tool — mirrors OpenClaw ``src/agents/tool-search.ts``.

Presents large tool inventories through search, describe, call, and code-mode tools.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable


from .tool_catalog import GLOBAL_TOOL_CATALOG, ToolCatalog, ToolDescriptor
from .tool_search_code_runner import CodeModeSubprocess

_log = logging.getLogger("jarvis.agents.tool_search")

TOOL_SEARCH_CODE_MODE_TOOL_NAME = "tool_search_code"
TOOL_SEARCH_RAW_TOOL_NAME = "tool_search"
TOOL_DESCRIBE_RAW_TOOL_NAME = "tool_describe"
TOOL_CALL_RAW_TOOL_NAME = "tool_call"

TOOL_SEARCH_CONTROL_TOOL_NAMES = {
    TOOL_SEARCH_CODE_MODE_TOOL_NAME,
    TOOL_SEARCH_RAW_TOOL_NAME,
    TOOL_DESCRIBE_RAW_TOOL_NAME,
    TOOL_CALL_RAW_TOOL_NAME,
}


def _compact_tool_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Compacts the output schema to save tokens, removing descriptions."""
    # Simplified version of compactToolOutputHint
    if not schema:
        return schema
    compacted = {}
    if "type" in schema:
        compacted["type"] = schema["type"]
    if "properties" in schema:
        compacted["properties"] = {
            k: _compact_tool_output_schema(v) for k, v in schema["properties"].items()
        }
    if "items" in schema:
        compacted["items"] = _compact_tool_output_schema(schema["items"])
    if "required" in schema:
        compacted["required"] = schema["required"]
    return compacted


class ToolSearchRuntime:
    """Manages Tool Search state and the code-mode bridge."""

    def __init__(
        self,
        catalog: ToolCatalog | None = None,
        execute_tool_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ):
        self.catalog = catalog or GLOBAL_TOOL_CATALOG
        self.execute_tool = execute_tool_callback

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """BM25-approximate search across the catalog."""
        all_tools = self.catalog.get_effective_inventory()

        keywords = [k.lower() for k in re.findall(r"\w+", query) if len(k) > 1]
        if not keywords:
            # Fallback to returning the first `limit` tools if no valid keywords
            return [
                {
                    "id": t.name,
                    "name": t.name,
                    "description": t.description,
                }
                for t in all_tools[:limit]
            ]

        scored: list[tuple[int, ToolDescriptor]] = []
        for tool in all_tools:
            score = 0
            name_lower = tool.name.lower()
            desc_lower = tool.description.lower()

            for kw in keywords:
                if kw in name_lower:
                    score += 5
                if kw in desc_lower:
                    score += 2

            if score > 0:
                scored.append((score, tool))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for _score, t in scored[:limit]:
            results.append(
                {
                    "id": t.name,
                    "name": t.name,
                    "description": t.description,
                }
            )
        return results

    def describe(self, tool_id: str) -> dict[str, Any] | None:
        """Returns the full schema descriptor for a tool."""
        tool = self.catalog.get(tool_id)
        if not tool or tool.quarantined:
            return None
        return {
            "id": tool.name,
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema,
        }

    def call(self, tool_id: str, args: dict[str, Any]) -> Any:
        """Dynamically calls a tool."""
        if not self.execute_tool:
            raise RuntimeError("No execute_tool_callback provided to ToolSearchRuntime")
        tool = self.catalog.get(tool_id)
        if not tool or tool.quarantined:
            raise ValueError(f"Tool {tool_id} not found or quarantined")

        return self.execute_tool(tool_id, args)

    def run_code_mode(self, code: str, timeout_ms: int = 10000) -> dict[str, Any]:
        """Runs the node subprocess bridge."""
        runner = CodeModeSubprocess(code, timeout_ms)

        def bridge_handler(msg: dict[str, Any]) -> Any:
            method = msg.get("method")
            args = msg.get("args", [])

            if method == "search":
                query = args[0] if len(args) > 0 else ""
                options = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
                limit = int(options.get("limit", 8))
                return self.search(query, limit)

            elif method == "describe":
                tool_id = args[0] if len(args) > 0 else ""
                desc = self.describe(str(tool_id))
                if not desc:
                    raise ValueError(f"Tool not found: {tool_id}")
                return desc

            elif method == "call":
                tool_id = args[0] if len(args) > 0 else ""
                call_args = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
                return self.call(str(tool_id), call_args)

            else:
                raise ValueError(f"Unknown bridge method: {method}")

        return runner.run(bridge_handler)


def get_tool_search_definitions() -> list[dict[str, Any]]:
    """Returns the JSON schemas for the tool search tools."""
    return [
        {
            "name": TOOL_SEARCH_CODE_MODE_TOOL_NAME,
            "description": "Execute JavaScript code in an isolated Node subprocess with access to openclaw.tools bridge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to execute. Can await openclaw.tools.search(), .describe(), and .call().",
                    }
                },
                "required": ["code"],
            },
        },
        {
            "name": TOOL_SEARCH_RAW_TOOL_NAME,
            "description": "Search available catalog tools by query string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query terms."},
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 8).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": TOOL_DESCRIBE_RAW_TOOL_NAME,
            "description": "Describe a specific catalog tool to get its full parameter schema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The exact ID of the tool to describe."}
                },
                "required": ["id"],
            },
        },
        {
            "name": TOOL_CALL_RAW_TOOL_NAME,
            "description": "Dynamically call a catalog tool by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The exact ID of the tool to call."},
                    "input": {
                        "type": "object",
                        "description": "The input parameters for the tool.",
                    },
                },
                "required": ["id", "input"],
            },
        },
    ]


__all__ = [
    "TOOL_SEARCH_CODE_MODE_TOOL_NAME",
    "TOOL_SEARCH_RAW_TOOL_NAME",
    "TOOL_DESCRIBE_RAW_TOOL_NAME",
    "TOOL_CALL_RAW_TOOL_NAME",
    "TOOL_SEARCH_CONTROL_TOOL_NAMES",
    "ToolSearchRuntime",
    "get_tool_search_definitions",
]
