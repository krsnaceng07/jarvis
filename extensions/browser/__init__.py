"""JARVIS Browser infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import BrowserPlugin, browser_plugin, entry
from .selenium_dom_engine import (
    SeleniumBrowserConfig,
    SeleniumDOMEngine,
    get_selenium_engine,
)

__all__ = [
    "BrowserPlugin",
    "browser_plugin",
    "entry",
    "SeleniumBrowserConfig",
    "SeleniumDOMEngine",
    "get_selenium_engine",
]
