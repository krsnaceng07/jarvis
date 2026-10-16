"""Fast memory and session context retrieval for low-latency voice responses."""

from __future__ import annotations

import asyncio
from typing import Any

from ..types import CallSession


async def search_fast_context(
    query: str,
    session: CallSession,
    timeout_ms: int = 1500,
    fallback_to_consult: bool = True,
    memory_provider: Any = None,
) -> dict[str, Any]:
    """Retrieve fast contextual snippets from memory/session within the strict timeout."""
    snippets: list[str] = []

    # 1. Search session transcript for keywords
    q_words = set(query.lower().split())
    for turn in reversed(session.transcript):
        if any(w in turn.text.lower() for w in q_words if len(w) > 3):
            snippets.append(f"[{turn.speaker.capitalize()}]: {turn.text}")
            if len(snippets) >= 3:
                break

    # 2. Query active memory provider if available within timeout
    if memory_provider and hasattr(memory_provider, "search"):
        try:
            timeout_sec = timeout_ms / 1000.0
            mem_task = asyncio.create_task(memory_provider.search(query, limit=3))
            done, _ = await asyncio.wait([mem_task], timeout=timeout_sec)
            if mem_task in done:
                mem_results = mem_task.result()
                if isinstance(mem_results, list):
                    for item in mem_results:
                        text = item.get("text") if isinstance(item, dict) else str(item)
                        snippets.append(f"[Memory]: {text}")
        except Exception:
            pass

    found = len(snippets) > 0
    return {
        "found": found,
        "snippets": snippets,
        "fallbackToConsult": fallback_to_consult and not found,
        "query": query,
    }
