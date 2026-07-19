"""WebSearchPlugin — JARVIS web search via OpenRouter → DDG fallback.

Migrated from ``actions/web_search.py``. Same algorithm, reorganized
into the OpenClaw 8-file shape.
"""

from __future__ import annotations

from typing import Any, cast

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)

from . import runtime

WEB_SEARCH_TOOL = ToolDecl(
    name="web_search",
    description=(
        "Performs a web search and returns a summary of the top results. "
        "Use mode='compare' to compare multiple items on a specific aspect."
    ),
    parameters=[
        ToolParam(
            name="query",
            type="string",
            description="The search query (required for mode='search').",
            required=False,
        ),
        ToolParam(
            name="mode",
            type="string",
            description="search | compare (default: search). 'compare' requires `items`.",
            required=False,
        ),
        ToolParam(
            name="items",
            type="string",
            description=(
                "Items to compare (comma-separated). Triggers 'compare' mode "
                "automatically when present."
            ),
            required=False,
        ),
        ToolParam(
            name="aspect",
            type="string",
            description="The aspect to compare on (e.g. 'price', 'camera quality').",
            required=False,
        ),
    ],
    returns="string",
    category="information",
)


class WebSearchPlugin(ToolPlugin):
    """Web search + compare tool. Stateless."""

    id = "tool_web_search"
    kind = "tool"
    version = "0.1.0"
    description = "Web search via OpenRouter → DDG fallback, plus compare."

    def init(self, ctx: Any) -> None:
        return

    async def shutdown(self) -> None:
        return None

    @property
    def tools(self) -> list[ToolDecl]:
        return [WEB_SEARCH_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        if name != "web_search":
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        return self._search(args)

    def _search(self, args: dict[str, Any]) -> Result[str]:
        query = (args.get("query") or "").strip()
        mode = (args.get("mode") or "search").lower().strip()
        items_raw: object = args.get("items") or []
        aspect = (args.get("aspect") or "general").strip() or "general"

        # `items` may be a list or a comma-separated string; normalize.
        items: list[str] = []
        if isinstance(items_raw, list):
            for entry in cast("list[object]", items_raw):
                s = str(entry).strip()
                if s:
                    items.append(s)
        elif isinstance(items_raw, str):
            items = [s.strip() for s in items_raw.split(",") if s.strip()]

        if not query and not items:
            return Err("Please provide a search query, sir.", code="MISSING_ARG")

        # Items present + no explicit mode → compare.
        if items and mode != "compare":
            mode = "compare"

        if mode == "compare":
            return Ok(runtime.compare(items, aspect))
        return Ok(runtime.search(query))


__all__ = ["WEB_SEARCH_TOOL", "WebSearchPlugin"]
