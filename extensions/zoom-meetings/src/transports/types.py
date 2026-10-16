"""Data structures and types for Zoom Meetings platform operations."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ZoomManualActionReason(str, Enum):
    BROWSER_JOIN_DISABLED = "browser_join_disabled"
    AUTHENTICATION_REQUIRED = "authentication_required"
    EMAIL_VERIFICATION_REQUIRED = "email_verification_required"
    PASSCODE_REQUIRED = "passcode_required"
    CAPTCHA_REQUIRED = "captcha_required"
    WAITING_ROOM_HOST_ADMISSION = "waiting_room_host_admission"
    DEVICE_PERMISSIONS_REQUIRED = "device_permissions_required"
    HOST_ENDED_MEETING = "host_ended_meeting"
    UNKNOWN = "unknown"


class ZoomPlatformState(str, Enum):
    IDLE = "idle"
    NAVIGATING = "navigating"
    INTERSTITIAL = "interstitial"
    PRE_JOIN = "pre_join"
    WAITING_ROOM = "waiting_room"
    IN_CALL = "in_call"
    ENDED = "ended"
    ERROR = "error"


@dataclass(slots=True)
class ZoomTranscriptEntry:
    speaker: str
    text: str
    timestamp: float = field(default_factory=time.time)
    is_final: bool = True


@dataclass(slots=True)
class ZoomMeetingSession:
    id: str
    url: str
    web_url: str
    meeting_id: str
    guest_name: str
    transport: str = "chrome"
    mode: str = "agent"
    status: ZoomPlatformState = ZoomPlatformState.IDLE
    manual_action: bool = False
    manual_action_reason: ZoomManualActionReason | None = None
    manual_action_message: str | None = None
    start_time: float = field(default_factory=time.time)
    in_call_time: float | None = None
    end_time: float | None = None
    transcript: list[ZoomTranscriptEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in (
            ZoomPlatformState.NAVIGATING,
            ZoomPlatformState.INTERSTITIAL,
            ZoomPlatformState.PRE_JOIN,
            ZoomPlatformState.WAITING_ROOM,
            ZoomPlatformState.IN_CALL,
        )

    @property
    def duration_seconds(self) -> float:
        if self.in_call_time is None:
            return 0.0
        end = self.end_time or time.time()
        return max(0.0, end - self.in_call_time)


@dataclass(slots=True)
class ZoomJoinResult:
    ok: bool
    session_id: str
    status: str
    manual_action: bool = False
    manual_action_reason: str | None = None
    manual_action_message: str | None = None
    error: str | None = None
