"""jarvis.system.web_search_provider — Live web search provider.

Mirrors OpenClaw's ddg-search-provider.ts. Provides live web information (news,
weather, prices, public data) with zero required API keys using DuckDuckGo search.
"""

from __future__ import annotations

import time
from typing import Any, Dict
import urllib.parse
import urllib.request
import json


class WebSearchProvider:
    """Live web search provider querying current online information."""

    @staticmethod
    def search(query: str, count: int = 5) -> Dict[str, Any]:
        """Perform live web search for query and return structured results."""
        query = query.strip()
        if not query:
            return {"ok": False, "error": "Query string is required.", "results": []}

        count = max(1, min(10, count))

        # 1. Try DuckDuckGo search library
        try:
            from duckduckgo_search import DDGS

            ddgs = DDGS()
            raw_results = list(ddgs.text(query, max_results=count))
            if raw_results:
                formatted = []
                for item in raw_results:
                    formatted.append({
                        "title": item.get("title", ""),
                        "url": item.get("href") or item.get("url", ""),
                        "snippet": item.get("body") or item.get("snippet", ""),
                        "source": "duckduckgo_live",
                        "retrieved_at": time.time(),
                    })
                return {
                    "ok": True,
                    "query": query,
                    "count": len(formatted),
                    "results": formatted,
                    "verified": True,
                }
        except Exception:
            pass

        # 2. Resilient fallback: DuckDuckGo instant answer / HTML lite endpoint
        try:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                abstract = data.get("AbstractText")
                if abstract:
                    results.append({
                        "title": data.get("Heading") or query,
                        "url": data.get("AbstractURL") or "https://duckduckgo.com",
                        "snippet": abstract,
                        "source": "duckduckgo_instant_api",
                        "retrieved_at": time.time(),
                    })
                for topic in data.get("RelatedTopics", [])[:count]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append({
                            "title": topic.get("Text", "")[:60],
                            "url": topic.get("FirstURL", ""),
                            "snippet": topic.get("Text", ""),
                            "source": "duckduckgo_instant_api",
                            "retrieved_at": time.time(),
                        })
                if results:
                    return {
                        "ok": True,
                        "query": query,
                        "count": len(results),
                        "results": results[:count],
                        "verified": True,
                    }
        except Exception:
            pass

        return {
            "ok": False,
            "error": "I could not retrieve fresh information right now.",
            "query": query,
            "results": [],
            "verified": False,
        }
