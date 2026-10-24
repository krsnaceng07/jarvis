"""jarvis.system.web_search_provider — Live web search provider.

Mirrors OpenClaw's ddg-search-provider.ts. Provides live web information (news,
weather, prices, public data) with zero required API keys using DuckDuckGo search.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict
import urllib.parse
import urllib.request
import warnings


# In-memory search cache with TTL for ultra-fast response on repeated / related queries
_SEARCH_CACHE: dict[str, tuple[float, Dict[str, Any]]] = {}
_SEARCH_CACHE_TTL_SEC: float = 300.0  # 5 minutes


class WebSearchProvider:
    """Live web search provider querying current online information."""

    @classmethod
    def search(
        cls,
        query: str,
        count: int = 5,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Perform live web search for query and return structured results."""
        if max_results is not None:
            count = max_results
        query = str(query or "").strip()
        if not query:
            return {"ok": False, "error": "Query string is required.", "results": []}

        count = max(1, min(10, count))
        cache_key = f"{query.lower()}:{count}"
        now = time.time()

        # Check in-memory cache for instant 0ms retrieval
        if cache_key in _SEARCH_CACHE:
            ts, cached_result = _SEARCH_CACHE[cache_key]
            if (now - ts) < _SEARCH_CACHE_TTL_SEC:
                return cached_result

        # 1. Try modern ddgs / DuckDuckGo search library with strict 3-second timeout
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS  # type: ignore

                ddgs_client = DDGS(timeout=3)
                raw_results = list(ddgs_client.text(query, max_results=count))
            if raw_results:
                formatted = []
                for item in raw_results:
                    formatted.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("href") or item.get("url", ""),
                            "snippet": item.get("body") or item.get("snippet", ""),
                            "source": "duckduckgo_live",
                            "retrieved_at": now,
                        }
                    )
                res = {
                    "ok": True,
                    "query": query,
                    "count": len(formatted),
                    "results": formatted,
                    "verified": True,
                }
                _SEARCH_CACHE[cache_key] = (now, res)
                return res
        except Exception:
            pass

        # 2. Resilient fallback: Direct DuckDuckGo HTML endpoint (no-dependency, fast, bypasses client lib issues)
        try:
            import re
            import html as html_lib
            encoded_data = urllib.parse.urlencode({"q": query}).encode()
            ddg_html_req = urllib.request.Request(
                "https://html.duckduckgo.com/html/",
                data=encoded_data,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(ddg_html_req, timeout=3.0) as resp:
                page = resp.read().decode("utf-8", errors="ignore")

            html_results = []
            blocks = re.split(r"<div[^>]+class=[\'\"][^\'\"]*result\s+results_links", page)
            for b in blocks[1:]:
                m_a = re.search(r"<a[^>]+class=[\'\"][^\'\"]*result__a[^\'\"]*[\'\"][^>]*href=[\'\"]([^\'\"]+)[\'\"][^>]*>(.*?)</a>", b, re.DOTALL)
                if not m_a:
                    continue
                raw_url = m_a.group(1)
                uddg = re.search(r"uddg=([^&]+)", raw_url)
                res_url = urllib.parse.unquote(uddg.group(1)) if uddg else raw_url
                res_title = html_lib.unescape(re.sub(r"<[^>]+>", "", m_a.group(2))).strip()

                m_snip = re.search(r"class=[\'\"][^\'\"]*result__snippet[^\'\"]*[\'\"][^>]*>(.*?)(?:</a>|</div>)", b, re.DOTALL)
                res_snip = ""
                if m_snip:
                    res_snip = html_lib.unescape(re.sub(r"<[^>]+>", "", m_snip.group(1))).strip()

                html_results.append({
                    "title": res_title,
                    "url": res_url,
                    "snippet": res_snip,
                    "source": "duckduckgo_html",
                    "retrieved_at": now,
                })
                if len(html_results) >= count:
                    break

            if html_results:
                res = {
                    "ok": True,
                    "query": query,
                    "count": len(html_results),
                    "results": html_results,
                    "verified": True,
                }
                _SEARCH_CACHE[cache_key] = (now, res)
                return res
        except Exception:
            pass

        # 3. Resilient fallback: DuckDuckGo instant answer / API endpoint with 2.5s timeout
        try:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                abstract = data.get("AbstractText")
                if abstract:
                    results.append(
                        {
                            "title": data.get("Heading") or query,
                            "url": data.get("AbstractURL") or "https://duckduckgo.com",
                            "snippet": abstract,
                            "source": "duckduckgo_instant_api",
                            "retrieved_at": now,
                        }
                    )
                for topic in data.get("RelatedTopics", [])[:count]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append(
                            {
                                "title": topic.get("Text", "")[:60],
                                "url": topic.get("FirstURL", ""),
                                "snippet": topic.get("Text", ""),
                                "source": "duckduckgo_instant_api",
                                "retrieved_at": now,
                            }
                        )
                if results:
                    res = {
                        "ok": True,
                        "query": query,
                        "count": len(results),
                        "results": results[:count],
                        "verified": True,
                    }
                    _SEARCH_CACHE[cache_key] = (now, res)
                    return res
        except Exception:
            pass

        return {
            "ok": False,
            "error": "I could not retrieve fresh information right now.",
            "query": query,
            "results": [],
            "verified": False,
        }

    @classmethod
    def format_results_for_prompt(cls, results: Any) -> str:
        """Format search results into human and model-readable text."""
        if isinstance(results, dict):
            if not results.get("ok", True) and results.get("error"):
                return f"Web search could not retrieve results: {results.get('error')}"
            items = results.get("results", [])
        elif isinstance(results, list):
            items = results
        else:
            items = []

        if not items:
            return "No web results found for this query."

        lines = ["### Web Search Results:"]
        for idx, item in enumerate(items, 1):
            if isinstance(item, dict):
                title = item.get("title", f"Result #{idx}")
                url = item.get("url", "")
                snippet = item.get("snippet", "")
            else:
                title = getattr(item, "title", f"Result #{idx}")
                url = getattr(item, "url", "")
                snippet = getattr(item, "snippet", "")
            lines.append(f"{idx}. **{title}**\n   URL: {url}\n   Snippet: {snippet}")
        return "\n\n".join(lines)
