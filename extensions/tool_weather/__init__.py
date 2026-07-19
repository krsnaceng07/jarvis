"""tool_weather — JARVIS weather tool (Phase 1A, refactored to use the SDK in 1B).

Mirrors OpenClaw's plugin-entry pattern. The actual ``WeatherPlugin``
class lives in ``plugin.py``; this file is the entry module that
``apps/desktop/src/jarvis_desktop/app.py`` imports to activate the plugin.

Usage (host side, see ``_load_plugin_entries`` in app.py)::

    from extensions.tool_weather import entry
    api = PluginApi(PluginContext(plugin_id=entry.id, plugin_kind=entry.kind))
    entry.register(api)
"""

from __future__ import annotations

from jarvis_sdk import (
    PluginApi,
    define_plugin_entry,
)

from .plugin import WeatherPlugin


def _register(api: PluginApi) -> None:
    """Register the weather tool with the host's PluginApi.

    Mirrors OpenClaw's ``api.registerTool(...)`` pattern. The host
    instantiates the ``WeatherPlugin`` class and registers it under
    its declared tool name(s).
    """
    api.register_tool(
        WeatherPlugin(),
        names=["weather_report"],
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="tool_weather",
    kind="tool",
    name="Weather",
    description="Current weather and forecasts via Google search.",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["network:outbound"],
)
