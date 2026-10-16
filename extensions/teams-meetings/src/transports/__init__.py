"""Teams Meetings transports barrel."""

from __future__ import annotations

from .chrome import (
    launch_chrome_teams,
    launch_chrome_teams_on_node,
    leave_chrome_teams,
    read_chrome_teams_transcript,
    recover_current_teams_tab,
)
from .chrome_browser_proxy import resolve_chrome_node_info
from .teams_page_scripts import (
    teams_leave_script,
    teams_status_script,
    teams_transcript_script,
)
from .teams_platform_adapter import (
    TEAMS_MEETINGS_PLATFORM_ADAPTER,
    TeamsMeetingsPlatformAdapter,
    is_talk_back_mode,
)
from .teams_platform_constants import (
    TEAMS_MEETINGS_NODE_COMMAND,
    TEAMS_MEETINGS_TOOL_NAME,
)
from .teams_urls import (
    is_recoverable_teams_tab,
    is_same_teams_url_for_reuse,
    normalize_teams_url_for_reuse,
)
from .types import (
    TEAMS_MEETINGS_TRANSCRIPT_MAX_LINES,
    TeamsMeetingsBrowserCandidateTab,
    TeamsMeetingsBrowserTab,
    TeamsMeetingsChromeHealth,
    TeamsMeetingsChromeSession,
    TeamsMeetingsJoinRequest,
    TeamsMeetingsJoinResult,
    TeamsMeetingsJoinResultSession,
    TeamsMeetingsManualAction,
    TeamsMeetingsSession,
    TeamsMeetingsTranscriptLine,
    TeamsMeetingsTranscriptSnapshot,
)

__all__ = [
    "TEAMS_MEETINGS_NODE_COMMAND",
    "TEAMS_MEETINGS_PLATFORM_ADAPTER",
    "TEAMS_MEETINGS_TOOL_NAME",
    "TEAMS_MEETINGS_TRANSCRIPT_MAX_LINES",
    "TeamsMeetingsBrowserCandidateTab",
    "TeamsMeetingsBrowserTab",
    "TeamsMeetingsChromeHealth",
    "TeamsMeetingsChromeSession",
    "TeamsMeetingsJoinRequest",
    "TeamsMeetingsJoinResult",
    "TeamsMeetingsJoinResultSession",
    "TeamsMeetingsManualAction",
    "TeamsMeetingsPlatformAdapter",
    "TeamsMeetingsSession",
    "TeamsMeetingsTranscriptLine",
    "TeamsMeetingsTranscriptSnapshot",
    "is_recoverable_teams_tab",
    "is_same_teams_url_for_reuse",
    "is_talk_back_mode",
    "launch_chrome_teams",
    "launch_chrome_teams_on_node",
    "leave_chrome_teams",
    "normalize_teams_url_for_reuse",
    "read_chrome_teams_transcript",
    "recover_current_teams_tab",
    "resolve_chrome_node_info",
    "teams_leave_script",
    "teams_status_script",
    "teams_transcript_script",
]
