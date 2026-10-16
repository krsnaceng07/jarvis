"""Runtime lifecycle coordinator for Zoom Meetings sessions."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from jarvis_sdk import Err, Ok, Result

from .config import ZoomMeetingsConfig
from .transports.types import (
    ZoomJoinResult,
    ZoomManualActionReason,
    ZoomMeetingSession,
    ZoomPlatformState,
    ZoomTranscriptEntry,
)
from .transports.zoom_platform_adapter import ZoomPlatformAdapter
from .zoom_url import extract_meeting_id, extract_passcode, normalize_zoom_url, to_zoom_web_app_url

logger = logging.getLogger(__name__)


class ZoomMeetingsRuntime:
    """Session coordinator and execution manager for Zoom Meetings."""

    def __init__(self, config: ZoomMeetingsConfig) -> None:
        self.config = config
        self._sessions: dict[str, ZoomMeetingSession] = {}
        self.adapter = ZoomPlatformAdapter(config)

    def find_session(self, session_id: str | None = None) -> ZoomMeetingSession | None:
        """Find an active or matching session by ID, or return the most recent active session."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        if not session_id and self._sessions:
            active = [s for s in self._sessions.values() if s.is_active]
            if active:
                return sorted(active, key=lambda s: s.start_time, reverse=True)[0]
            return sorted(self._sessions.values(), key=lambda s: s.start_time, reverse=True)[0]

        return None

    async def join(
        self,
        *,
        url: str | None = None,
        guest_name: str | None = None,
        mode: str | None = None,
        passcode: str | None = None,
        metadata: dict[str, Any] | None = None,
        simulated_page_text: str | None = None,
    ) -> Result[ZoomJoinResult, str]:
        """Join a Zoom meeting as a guest through the Zoom Web Client."""
        target_url = url or self.config.defaults.meeting
        if not target_url:
            return Err(
                "Zoom meeting URL is required (none provided or configured in defaults.meeting)"
            )

        try:
            norm_url = normalize_zoom_url(target_url)
        except ValueError as ex:
            return Err(f"Invalid Zoom meeting URL: {ex}")

        name = guest_name or self.config.chrome.guest_name or "JARVIS"
        req_mode = mode or self.config.default_mode or "agent"
        pwd = passcode or extract_passcode(norm_url) or self.config.chrome.passcode
        meeting_id = extract_meeting_id(norm_url) or "meeting"
        web_url = to_zoom_web_app_url(norm_url, guest_name=name)

        sess_meta = dict(metadata or {})
        if pwd:
            sess_meta["passcode"] = pwd

        session_id = f"zoom_{uuid.uuid4().hex[:10]}"
        session = ZoomMeetingSession(
            id=session_id,
            url=norm_url,
            web_url=web_url,
            meeting_id=meeting_id,
            guest_name=name,
            transport=self.config.default_transport,
            mode=req_mode,
            status=ZoomPlatformState.NAVIGATING,
            metadata=sess_meta,
        )

        self._sessions[session_id] = session

        # Evaluate simulated or live page state
        if simulated_page_text is not None:
            is_manual, reason, msg = self.adapter.analyze_dom_text(simulated_page_text)
            if is_manual:
                session.manual_action = True
                session.manual_action_reason = reason
                session.manual_action_message = msg
                session.status = (
                    ZoomPlatformState.WAITING_ROOM
                    if reason == ZoomManualActionReason.WAITING_ROOM_HOST_ADMISSION
                    else ZoomPlatformState.PRE_JOIN
                )
                return Ok(
                    ZoomJoinResult(
                        ok=True,
                        session_id=session.id,
                        status=session.status.value,
                        manual_action=True,
                        manual_action_reason=reason.value if reason else None,
                        manual_action_message=msg,
                    )
                )

        # Transition into in_call state
        session.status = ZoomPlatformState.IN_CALL
        session.in_call_time = time.time()

        # Add initial intro message if configured
        if self.config.realtime.intro_message and req_mode in ("agent", "bidi", "speak"):
            session.transcript.append(
                ZoomTranscriptEntry(
                    speaker=name,
                    text=self.config.realtime.intro_message,
                    timestamp=time.time(),
                )
            )

        return Ok(
            ZoomJoinResult(
                ok=True,
                session_id=session.id,
                status=session.status.value,
                manual_action=False,
            )
        )

    async def leave(self, session_id: str | None = None) -> Result[bool, str]:
        """Leave an active Zoom meeting session."""
        session = self.find_session(session_id)
        if not session:
            return Err("No matching Zoom meeting session found to leave")

        session.status = ZoomPlatformState.ENDED
        session.end_time = time.time()
        return Ok(True)

    async def get_status(self, session_id: str | None = None) -> Result[dict[str, Any], str]:
        """Inspect active session status and manual action states."""
        session = self.find_session(session_id)
        if not session:
            return Ok({"active": False, "session": None})

        return Ok(
            {
                "active": session.is_active,
                "session": {
                    "id": session.id,
                    "meetingId": session.meeting_id,
                    "url": session.url,
                    "webUrl": session.web_url,
                    "guestName": session.guest_name,
                    "transport": session.transport,
                    "mode": session.mode,
                    "status": session.status.value,
                    "manualAction": session.manual_action,
                    "manualActionReason": (
                        session.manual_action_reason.value if session.manual_action_reason else None
                    ),
                    "manualActionMessage": session.manual_action_message,
                    "durationSeconds": session.duration_seconds,
                    "transcriptCount": len(session.transcript),
                },
            }
        )

    async def get_transcript(
        self, session_id: str | None = None
    ) -> Result[list[dict[str, Any]], str]:
        """Retrieve live captions and conversation transcript entries."""
        session = self.find_session(session_id)
        if not session:
            return Ok([])

        return Ok(
            [
                {
                    "speaker": t.speaker,
                    "text": t.text,
                    "timestamp": t.timestamp,
                    "isFinal": t.is_final,
                }
                for t in session.transcript
            ]
        )

    async def speak(self, text: str, session_id: str | None = None) -> Result[dict[str, Any], str]:
        """Speak a text message into the meeting audio bridge."""
        if not text or not text.strip():
            return Err("Speech text is required")

        session = self.find_session(session_id)
        if not session:
            return Err("No active Zoom meeting session found to speak into")

        entry = ZoomTranscriptEntry(
            speaker=session.guest_name,
            text=text.strip(),
            timestamp=time.time(),
        )
        session.transcript.append(entry)

        return Ok(
            {
                "ok": True,
                "sessionId": session.id,
                "spokenText": text.strip(),
                "speaker": session.guest_name,
            }
        )
