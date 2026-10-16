"""Extraction pipeline: HTML to Markdown/Text, with provider fallback."""

from typing import Dict, Any, Tuple

try:
    from readability import Document  # type: ignore
    from markdownify import markdownify  # type: ignore
except ImportError:
    Document = None
    markdownify = None

from .config import ResolvedWebFetchConfig


def extract_content(html: bytes, url: str, extract_mode: str, max_chars: int) -> Tuple[str, str]:
    """Extract content using Readability."""
    if Document is None or markdownify is None:
        raise RuntimeError("Readability libraries not installed.")

    try:
        html_str = html.decode("utf-8", errors="replace")
        doc = Document(html_str)
        content_html = doc.summary()

        if extract_mode == "markdown":
            extracted = markdownify(content_html, heading_style="ATX")
        else:
            # Simple text extraction fallback
            import re

            extracted = re.sub(r"<[^>]+>", "", content_html)

        return extracted.strip(), "readability"
    except Exception as e:
        raise RuntimeError(f"Readability extraction failed: {e}")


async def fallback_to_provider(
    url: str, config: ResolvedWebFetchConfig
) -> Tuple[str, str, Dict[str, Any]]:
    """Fallback to external provider (e.g., Firecrawl)."""
    provider_name = config.provider
    if not provider_name:
        # Default auto-detect: try firecrawl if loaded in the environment
        # For simplicity in this implementation we check if we can import the firecrawl plugin
        provider_name = "firecrawl"

    if provider_name == "firecrawl":
        # Usually we would call the contract provided by the firecrawl plugin.
        # Since firecrawl is an infra stub, we simulate a failure or basic fallback.
        raise NotImplementedError("Firecrawl provider integration is stubbed.")

    raise RuntimeError(f"No configured fetch provider found for fallback: {provider_name}")
