"""jarvis.agents.sessions.tools.web_search_tool — Real-time live web search tool.

OpenClaw parity:
Matches OpenClaw's duckduckgo extension (extensions/duckduckgo/src/ddg-search-provider.ts)
allowing the agent to look up real-time live information (weather, news, current facts,
stock/crypto prices, flight status) without requiring an API key.
"""

from __future__ import annotations

from typing import Any, Optional

from src.system.web_search_provider import WebSearchProvider
from .tool_definition_wrapper import AgentTool


def create_web_search_tool_definition() -> dict[str, Any]:
    return {
        "name": "web_search",
        "description": (
            "Search the live web for real-time information, current news, weather, stock prices, or facts. "
            "Returns relevant web snippets with titles and source URLs. "
            "Use this tool whenever the user asks about current events, today's weather, latest information, "
            "or facts not present in your local host environment."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "The search query string (e.g. 'weather in Kathmandu today', 'latest tech news').",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Maximum number of search results to return (default: 5, max: 10).",
                },
            },
            "required": ["query"],
        },
    }


def create_web_search_tool(options: Optional[dict[str, Any]] = None) -> AgentTool:
    """Create runtime web_search AgentTool backed by WebSearchProvider."""
    definition = create_web_search_tool_definition()

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> Any:
        query = str(params.get("query", "")).strip()
        if not query:
            return {
                "content": [{"type": "text", "text": "Error: 'query' parameter is required for web_search."}]
            }

        max_results = int(params.get("max_results", 5))
        try:
            results = await WebSearchProvider.search(query=query, max_results=max_results)
            formatted = WebSearchProvider.format_results_for_prompt(results)
            return {
                "content": [{"type": "text", "text": formatted}],
                "data": {"query": query, "count": len(results), "results": [r.to_dict() for r in results]},
            }
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Web search failed: {exc}"}]
            }

    return {
        "name": definition["name"],
        "label": "Web Search",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


__all__ = ["create_web_search_tool", "create_web_search_tool_definition"]
