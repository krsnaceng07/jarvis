"""tool_web_search — JARVIS web search (Phase 1C).

Migrated from ``actions/web_search.py``. Same behavior, OpenClaw shape.
"""
from __future__ import annotations

from jarvis_sdk import PluginApi, define_plugin_entry

from .plugin import WebSearchPlugin


def _register(api: PluginApi) -> None:
    api.register_tool(
        WebSearchPlugin(),
        names=["web_search"],
    )


entry = define_plugin_entry(
    id="tool_web_search",
    kind="tool",
    name="Web Search",
    description="Web search via OpenRouter → DDG fallback, plus compare.",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["network:outbound"],
)
