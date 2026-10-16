"""The web_fetch tool definition and execution layer."""

import time
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel, ConfigDict
import asyncio

from .config import resolve_web_fetch_config
from .fetch_engine import perform_fetch
from .extractor import extract_content, fallback_to_provider


class WebFetchArgs(BaseModel):
    url: str
    extractMode: str = "markdown"
    maxChars: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class WebFetchTool:
    """Fetch and extract readable content from a URL."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch readable web content via HTTP GET (no JS execution). Extracts to markdown or text."

    @property
    def schema(self) -> Any:
        return WebFetchArgs

    def __init__(self):
        super().__init__()
        # Simple memory cache: URL -> (timestamp, result_dict)
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    async def execute(self, ctx: Any, args: WebFetchArgs) -> Dict[str, Any]:
        """Execute the web_fetch tool."""

        # Load and resolve configuration
        # In a real setup, we might read from the global gateway config.
        # Here we mock reading from context or using default.
        raw_config = (
            ctx.config.get("tools", {}).get("web", {}).get("fetch", {})
            if hasattr(ctx, "config")
            else {}
        )
        config = resolve_web_fetch_config(raw_config)

        if not config.enabled:
            raise RuntimeError("web_fetch tool is disabled by configuration.")

        # Apply maxChars caps
        req_max_chars = args.maxChars if args.maxChars is not None else config.maxChars
        max_chars = min(req_max_chars, config.maxCharsCap)

        cache_ttl_seconds = config.cacheTtlMinutes * 60
        now = time.time()

        # Check cache
        if args.url in self._cache:
            cached_time, cached_res = self._cache[args.url]
            if now - cached_time < cache_ttl_seconds:
                # Return cache hit
                cached_copy = dict(cached_res)
                cached_copy["cached"] = True
                return cached_copy

        # Start progress timer (emits public progress after 5s)
        progress_task = asyncio.create_task(self._emit_progress_delayed(ctx))

        try:
            start_time = time.time()
            extracted_text = ""
            extractor = ""
            final_url = args.url
            status = 200

            try:
                if config.readability:
                    raw_html, response = await perform_fetch(args.url, config)
                    final_url = str(response.url)
                    status = response.status_code

                    if status >= 400:
                        raise RuntimeError(f"HTTP Error: {status}")

                    extracted_text, extractor = extract_content(
                        raw_html, final_url, args.extractMode, max_chars
                    )
                else:
                    raise RuntimeError("Readability disabled, falling back immediately.")

            except Exception as e:
                # Fallback to provider
                try:
                    extracted_text, extractor, fallback_meta = await fallback_to_provider(
                        args.url, config
                    )
                    # Merge metadata if needed
                except Exception as fallback_e:
                    raise RuntimeError(f"Fetch failed: {e}. Fallback also failed: {fallback_e}")

            took_ms = int((time.time() - start_time) * 1000)

            raw_length = len(extracted_text)
            truncated = False
            if raw_length > max_chars:
                extracted_text = extracted_text[:max_chars]
                truncated = True

            result = {
                "url": args.url,
                "finalUrl": final_url,
                "status": status,
                "extractMode": args.extractMode,
                "extractor": extractor,
                "externalContent": True,
                "truncated": truncated,
                "length": len(extracted_text),
                "rawLength": raw_length,
                "fetchedAt": int(now * 1000),
                "tookMs": took_ms,
                "text": extracted_text,
            }

            # Cache the result
            self._cache[args.url] = (time.time(), result)

            return result

        finally:
            progress_task.cancel()

    async def _emit_progress_delayed(self, ctx: Any):
        try:
            await asyncio.sleep(5.0)
            # Emit progress update. The API depends on JARVIS context channels.
            if hasattr(ctx, "send_progress"):
                await ctx.send_progress("Fetching page content...")
        except asyncio.CancelledError:
            pass


web_fetch_tool = WebFetchTool()
