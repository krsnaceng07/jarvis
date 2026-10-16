"""jarvis.application_automation.applications.youtube.state_machine — YouTube finite state machine.

Defines valid states and transitions for the YouTube interaction lifecycle.
"""

from __future__ import annotations

from typing import Dict, Set

from ...state_machine import ApplicationStateMachine

# Canonical YouTube States
STATE_UNINITIALIZED = "UNINITIALIZED"
STATE_HOME = "HOME"
STATE_SEARCHING = "SEARCHING"
STATE_SEARCH_RESULTS = "SEARCH_RESULTS"
STATE_WATCH_PAGE = "WATCH_PAGE"
STATE_AD_PLAYING = "AD_PLAYING"
STATE_VIDEO_PLAYING = "VIDEO_PLAYING"
STATE_VIDEO_PAUSED = "VIDEO_PAUSED"

YOUTUBE_VALID_TRANSITIONS: Dict[str, Set[str]] = {
    STATE_UNINITIALIZED: {STATE_HOME, STATE_SEARCH_RESULTS, STATE_WATCH_PAGE},
    STATE_HOME: {STATE_SEARCHING, STATE_WATCH_PAGE, STATE_HOME},
    STATE_SEARCHING: {STATE_SEARCH_RESULTS, STATE_HOME, STATE_SEARCHING},
    STATE_SEARCH_RESULTS: {STATE_WATCH_PAGE, STATE_SEARCHING, STATE_HOME, STATE_SEARCH_RESULTS},
    STATE_WATCH_PAGE: {
        STATE_AD_PLAYING,
        STATE_VIDEO_PLAYING,
        STATE_VIDEO_PAUSED,
        STATE_SEARCHING,
        STATE_HOME,
    },
    STATE_AD_PLAYING: {STATE_VIDEO_PLAYING, STATE_VIDEO_PAUSED, STATE_WATCH_PAGE},
    STATE_VIDEO_PLAYING: {
        STATE_VIDEO_PAUSED,
        STATE_WATCH_PAGE,
        STATE_SEARCHING,
        STATE_HOME,
        STATE_AD_PLAYING,
    },
    STATE_VIDEO_PAUSED: {
        STATE_VIDEO_PLAYING,
        STATE_WATCH_PAGE,
        STATE_SEARCHING,
        STATE_HOME,
        STATE_AD_PLAYING,
    },
}


class YouTubeStateMachine(ApplicationStateMachine):
    """Finite state machine specialized for YouTube player and page navigation."""

    def __init__(self, initial_state: str = STATE_UNINITIALIZED) -> None:
        super().__init__(
            initial_state=initial_state,
            valid_transitions=YOUTUBE_VALID_TRANSITIONS,
        )
