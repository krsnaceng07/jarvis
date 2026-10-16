"""Zoom Meetings platform adapters and transport types."""

from .types import (
    ZoomJoinResult,
    ZoomManualActionReason,
    ZoomMeetingSession,
    ZoomPlatformState,
    ZoomTranscriptEntry,
)
from .zoom_platform_adapter import ZoomPlatformAdapter

__all__ = [
    "ZoomJoinResult",
    "ZoomManualActionReason",
    "ZoomMeetingSession",
    "ZoomPlatformState",
    "ZoomTranscriptEntry",
    "ZoomPlatformAdapter",
]
