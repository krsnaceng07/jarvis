"""MemoryCorePlugin — the memory_search + memory_get tools.

Phase 2 ships substring search only. Semantic search via LanceDB
lands in Phase 2.5.
"""
from __future__ import annotations

from typing import Any

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)


MEMORY_SEARCH_TOOL = ToolDecl(
    name="memory_search",
    description=(
        "Searches JARVIS's long-term memory. Returns matching entries "
        "(key: value) for the given query. Phase 2 is substring-based; "
        "semantic search lands in Phase 2.5 (LanceDB backend)."
    ),
    parameters=[
        ToolParam(
            name="query",
            type="string",
            description="Substring to search for in memory values.",
            required=True,
        ),
        ToolParam(
            name="limit",
            type="integer",
            description="Max results (default: 20).",
            required=False,
        ),
    ],
    returns="string",
    category="memory",
)

MEMORY_GET_TOOL = ToolDecl(
    name="memory_get",
    description=(
        "Reads a single memory entry by its key. Returns the value "
        "string or an error if the key is missing."
    ),
    parameters=[
        ToolParam(
            name="key",
            type="string",
            description="The memory key to read.",
            required=True,
        ),
    ],
    returns="string",
    category="memory",
)


class MemoryCorePlugin(ToolPlugin):
    """Memory search + get tools (Phase 2: substring backend)."""

    id = "memory_core"
    kind = "memory"
    version = "0.1.0"
    description = "Long-term memory (substring search + key/value get)."

    def init(self, ctx: Any) -> None:
        return

    async def shutdown(self) -> None:
        return None

    @property
    def tools(self) -> list[ToolDecl]:
        return [MEMORY_SEARCH_TOOL, MEMORY_GET_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        # Lazy import to avoid pulling sqlite3 at import time.
        from .runtime import MemoryRuntime

        if name == "memory_search":
            return self._search(args, MemoryRuntime.default())
        if name == "memory_get":
            return self._get(args, MemoryRuntime.default())
        return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")

    def _search(self, args: dict[str, Any], runtime) -> Result[str]:
        query = (args.get("query") or "").strip()
        if not query:
            return Err("memory_search needs a non-empty query, sir.", code="MISSING_ARG")
        limit = int(args.get("limit") or 20)
        rows = runtime.search_substring(query, limit=limit)
        if not rows:
            return Ok(f"No memory entries match {query!r}.")
        body = "\n".join(f"  - {r['key']}: {r['value']}" for r in rows)
        return Ok(f"Memory matches for {query!r}:\n{body}")

    def _get(self, args: dict[str, Any], runtime) -> Result[str]:
        key = (args.get("key") or "").strip()
        if not key:
            return Err("memory_get needs a non-empty key, sir.", code="MISSING_ARG")
        value = runtime.get(key)
        if value is None:
            return Err(f"No memory entry with key {key!r}.", code="NOT_FOUND")
        return Ok(f"{key}: {value}")


__all__ = [
    "MEMORY_GET_TOOL",
    "MEMORY_SEARCH_TOOL",
    "MemoryCorePlugin",
]
