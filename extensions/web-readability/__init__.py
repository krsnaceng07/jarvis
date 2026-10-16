"""Web Readability extension root entrypoint."""

from __future__ import annotations

from .src.extractor import (
    HTML_VOID_TAGS,
    READABILITY_MAX_ESTIMATED_NESTING_DEPTH,
    READABILITY_MAX_HTML_CHARS,
    ReadabilityWebContentExtractor,
    WebContentExtractionRequest,
    WebContentExtractionResult,
    create_readability_web_content_extractor,
    exceeds_estimated_html_nesting_depth,
    normalize_whitespace,
    strip_invisible_unicode,
)
from .src.plugin import WebReadabilityPlugin, entry, web_readability_plugin

__all__ = [
    "HTML_VOID_TAGS",
    "READABILITY_MAX_ESTIMATED_NESTING_DEPTH",
    "READABILITY_MAX_HTML_CHARS",
    "ReadabilityWebContentExtractor",
    "WebContentExtractionRequest",
    "WebContentExtractionResult",
    "WebReadabilityPlugin",
    "create_readability_web_content_extractor",
    "entry",
    "exceeds_estimated_html_nesting_depth",
    "normalize_whitespace",
    "strip_invisible_unicode",
    "web_readability_plugin",
]
