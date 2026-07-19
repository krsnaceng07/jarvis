"""tool_youtube_video — JARVIS YouTube controller (Phase 1C)."""

from __future__ import annotations

from jarvis_sdk import PluginApi, define_plugin_entry

from .plugin import YouTubeVideoPlugin


def _register(api: PluginApi) -> None:
    api.register_tool(
        YouTubeVideoPlugin(),
        names=["youtube_video"],
    )


entry = define_plugin_entry(
    id="tool_youtube_video",
    kind="tool",
    name="YouTube",
    description="YouTube play / summarize / get_info / trending.",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["network:outbound", "fs:write:desktop"],
)
