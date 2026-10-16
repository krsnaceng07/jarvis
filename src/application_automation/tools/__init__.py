"""jarvis.application_automation.tools — Application automation tool functions."""

from .youtube_tools import (
    YOUTUBE_TOOL_DECLARATIONS,
    dispatch_youtube_tool,
    youtube_get_state_tool,
    youtube_pause_tool,
    youtube_play_tool,
    youtube_resume_tool,
    youtube_search_tool,
    youtube_set_volume_tool,
    youtube_skip_ad_tool,
    youtube_subscribe_tool,
    youtube_unsubscribe_tool,
    youtube_close_tool,
)

__all__ = [
    "YOUTUBE_TOOL_DECLARATIONS",
    "dispatch_youtube_tool",
    "youtube_get_state_tool",
    "youtube_pause_tool",
    "youtube_play_tool",
    "youtube_resume_tool",
    "youtube_search_tool",
    "youtube_set_volume_tool",
    "youtube_skip_ad_tool",
    "youtube_subscribe_tool",
    "youtube_unsubscribe_tool",
    "youtube_close_tool",
]
