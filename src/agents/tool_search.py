"""Tool search tool — mirrors OpenClaw ``src/agents/tool-search.ts``."""

from __future__ import annotations

import re
from typing import Any
from .tool_catalog import GLOBAL_TOOL_CATALOG, ToolCatalog, ToolDescriptor

TOOL_SEARCH_TOOL_NAME = "tool_search"


def tool_search_query(
    query: str,
    catalog: ToolCatalog | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search catalog tools matching query terms in name or description."""
    cat = catalog or GLOBAL_TOOL_CATALOG
    all_tools = cat.get_effective_inventory()

    keywords = [k.lower() for k in re.findall(r"\w+", query) if len(k) > 1]
    if not keywords:
        return []

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
        results.append({
            "name": t.name,
            "description": t.description,
            "source": t.source,
        })
    return results


__all__ = ["TOOL_SEARCH_TOOL_NAME", "tool_search_query"]
