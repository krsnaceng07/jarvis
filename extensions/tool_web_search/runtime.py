"""Runtime helpers for tool_web_search.

Phase 1C: the actual search backends. The plugin (``plugin.py``) is
a thin wrapper; this module owns the OpenRouter → DDG fallback chain
and the result formatter.

Mirrors OpenClaw's per-extension ``runtime.ts`` pattern: heavy
imports and side effects live here, not in the entry module.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]
    # extensions/tool_web_search/runtime.py → 2 parents up = workspace root


BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def openrouter_chat(query: str) -> str:
    """Call the OpenRouter client with a web-search-style system prompt.

    Mirrors the legacy `actions/web_search.py` block. Falls back to
    ``ddg_search`` on any exception.
    """
    from or_client import client

    return client.chat(
        query,
        system="You are a web search assistant. Answer factually and concisely.",
    )


def ddg_search(query: str, max_results: int = 6) -> list[dict[str, str]]:
    """DuckDuckGo text search. Returns ``[{"title", "snippet", "url"}]``."""
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]
    except ImportError:
        from duckduckgo_search import DDGS  # type: ignore[no-redef,import-not-found]

    results: list[dict[str, str]] = []
    with DDGS() as ddgs:  # type: ignore[no-redef]
        ddgs_obj: Any = ddgs
        text_fn: Callable[..., Any] = ddgs_obj.text
        for r in text_fn(query, max_results=max_results):
            r_obj: Any = r
            r_dict: dict[str, object] = dict(r_obj)  # type: ignore[arg-type]
            row: dict[str, str] = {
                "title": str(r_dict.get("title", "") or ""),
                "snippet": str(r_dict.get("body", "") or ""),
                "url": str(r_dict.get("href", "") or ""),
            }
            results.append(row)
    return results


def format_ddg(query: str, results: list[dict[str, str]]) -> str:
    """Render DDG results as a human-readable text block."""
    if not results:
        return f"No results found for: {query}"
    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):
            lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def search(query: str) -> str:
    """Run the full search chain: OpenRouter → DDG fallback → Err message.

    Phase 1C contract: never raises. Every error is reported as a
    human-readable string so the LLM can react.
    """
    print(f"[WebSearch] query: {query!r}")
    try:
        result = openrouter_chat(query)
        print("[WebSearch] OpenRouter OK.")
        return result
    except Exception as e:
        print(f"[WebSearch] OpenRouter failed ({e}) — trying DDG...")
    try:
        results = ddg_search(query)
        return format_ddg(query, results)
    except Exception as e:
        return f"Search failed, sir: {e}"


def compare(items: list[str], aspect: str) -> str:
    """Compare ``items`` on ``aspect`` (e.g. 'iPhone 15 vs Pixel 8 on camera')."""
    if not items:
        return "Please provide at least one item to compare, sir."
    aspect = aspect.strip() or "general"
    query = f"Compare {', '.join(items)} in terms of {aspect}. Give specific facts and data."

    try:
        return openrouter_chat(query)
    except Exception as e:
        print(f"[WebSearch] compare via OpenRouter failed ({e}) — DDG fallback")

    lines = [f"Comparison — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        try:
            for r in ddg_search(f"{item} {aspect}", max_results=3)[:2]:
                if r.get("snippet"):
                    lines.append(f"  • {r['snippet']}")
        except Exception:
            lines.append("  • (no data)")
    return "\n".join(lines)


__all__ = ["compare", "ddg_search", "format_ddg", "openrouter_chat", "search"]
