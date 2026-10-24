"""YouTube tool plugin definition.

OpenClaw parity: mirrors the OpenClaw media and tool extension pattern.
Binds YouTube media search, playback, volume, and ad-skipping into the tool registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin, PluginApi


@dataclass(frozen=True, slots=True)
class YouTubePlugin(Plugin):
    """YouTube tool descriptor and runtime coordinator."""

    id: str = "youtube"
    name: str = "YouTube"
    kind: str = "tool"
    version: str = "0.1.0"
    description: str = "YouTube video search, playback control, tab affinity, and ad-skipping."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Plugin initialization hook."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register YouTube granular tools with the agent runtime."""
        if hasattr(api, "register_tool"):
            try:
                from src.application_automation.tools.youtube_tools import (
                    youtube_close_tool,
                    youtube_get_state_tool,
                    youtube_pause_tool,
                    youtube_play_tool,
                    youtube_resume_tool,
                    youtube_search_tool,
                    youtube_set_volume_tool,
                    youtube_skip_ad_tool,
                    youtube_subscribe_tool,
                    youtube_unsubscribe_tool,
                )

                for tool_fn in [
                    youtube_play_tool,
                    youtube_pause_tool,
                    youtube_resume_tool,
                    youtube_search_tool,
                    youtube_skip_ad_tool,
                    youtube_set_volume_tool,
                    youtube_get_state_tool,
                    youtube_subscribe_tool,
                    youtube_unsubscribe_tool,
                    youtube_close_tool,
                ]:
                    api.register_tool(tool_fn)
            except ImportError:
                pass



youtube_plugin = YouTubePlugin()
entry = youtube_plugin
