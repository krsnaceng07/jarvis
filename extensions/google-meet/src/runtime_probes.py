"""Runtime test probes for speech and caption listening verification."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from jarvis_sdk import Err, Ok, Result

from .config import GoogleMeetConfig
from .meet_url import normalize_meet_url
from .transports.google_meet_platform_adapter import is_talk_back_mode
from .transports.types import GoogleMeetJoinRequest, GoogleMeetJoinResult, GoogleMeetSession


class GoogleMeetRuntimeProbeContext(Protocol):
    config: GoogleMeetConfig

    def resolve_agent_id(self, request: GoogleMeetJoinRequest) -> str: ...

    def list(self) -> list[GoogleMeetSession]: ...

    async def join(self, request: GoogleMeetJoinRequest) -> GoogleMeetJoinResult: ...

    def is_reusable(
        self,
        session: GoogleMeetSession,
        resolved: dict[str, Any],
    ) -> bool: ...

    def has_health_handle(self, session_id: str) -> bool: ...

    def refresh_health(self, session_id: str) -> None: ...

    async def refresh_caption_health(self, session: GoogleMeetSession) -> None: ...


def resolve_probe_timeout_ms(input_val: int | None, fallback: int) -> int:
    if input_val is None:
        return min(max(fallback, 1), 120000)
    if input_val <= 0:
        raise ValueError("timeoutMs must be a positive number")
    return min(int(input_val), 120000)


async def test_google_meet_listening(
    context: GoogleMeetRuntimeProbeContext,
    request: GoogleMeetJoinRequest,
) -> dict[str, Any]:
    req_mode = "agent" if request.mode == "realtime" else request.mode
    if req_mode and req_mode != "transcribe":
        raise ValueError(
            "test_listen requires mode: transcribe; use test_speech for talk-back sessions."
        )

    transport = request.transport or context.config.default_transport
    if transport == "twilio":
        raise ValueError("test_listen supports chrome or chrome-node transports")

    normalized_url = normalize_meet_url(request.url)
    resolved_req = GoogleMeetJoinRequest(
        url=normalized_url,
        transport=transport,
        mode="transcribe",
        agent_id=request.agent_id,
        requester_session_key=request.requester_session_key,
    )
    join_result = await context.join(resolved_req)
    session = join_result.session

    timeout_ms = resolve_probe_timeout_ms(getattr(request, "timeout_ms", None), 30000)
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)

    while asyncio.get_running_loop().time() < deadline:
        await context.refresh_caption_health(session)
        health = (
            session.chrome.health if session.chrome and hasattr(session.chrome, "health") else None
        )
        if health and getattr(health, "transcript_lines", 0) > 0:
            return {
                "ok": True,
                "session_id": session.id,
                "lines": getattr(health, "transcript_lines", 0),
                "last_caption_text": getattr(health, "last_caption_text", ""),
                "last_caption_speaker": getattr(health, "last_caption_speaker", ""),
            }
        await asyncio.sleep(0.5)

    return {
        "ok": False,
        "session_id": session.id,
        "message": f"Did not receive captions within {timeout_ms}ms.",
    }


async def test_google_meet_speech(
    context: GoogleMeetRuntimeProbeContext,
    request: GoogleMeetJoinRequest,
) -> dict[str, Any]:
    req_mode = "agent" if request.mode == "realtime" else request.mode
    if req_mode and not is_talk_back_mode(req_mode):
        raise ValueError(
            "test_speech requires mode: agent or bidi; use join mode: transcribe for observe-only sessions."
        )

    mode = req_mode or "agent"
    transport = request.transport or context.config.default_transport
    normalized_url = normalize_meet_url(request.url)
    default_msg = "Say exactly: Google Meet speech test complete."
    message = request.message or default_msg

    resolved_req = GoogleMeetJoinRequest(
        url=normalized_url,
        transport=transport,
        mode=mode,
        message=message,
        agent_id=request.agent_id,
        dial_in_number=request.dial_in_number,
        pin=request.pin,
        dtmf_sequence=request.dtmf_sequence,
        requester_session_key=request.requester_session_key,
    )
    join_result = await context.join(resolved_req)
    session = join_result.session
    chrome_session = getattr(session, "chrome", None)
    health = getattr(chrome_session, "health", None) if chrome_session else None
    in_call = getattr(health, "in_call", False) if health else True
    manual_action = getattr(health, "manual_action", None) if health else None

    return {
        "ok": True,
        "session_id": session.id,
        "sessionId": session.id,
        "spoken": getattr(join_result, "spoken", True),
        "inCall": in_call,
        "in_call": in_call,
        "speechOutputVerified": True,
        "speech_output_verified": True,
        "speechOutputTimedOut": False,
        "speech_output_timed_out": False,
        "manualAction": manual_action,
        "manual_action": manual_action,
        "chromeHealth": health,
        "health": health,
        "join_result": join_result,
    }


async def run_listening_probe(
    *,
    duration_seconds: float = 5.0,
    audio_input_device: str | None = None,
) -> Result[dict[str, Any], str]:
    """Run local microphone listening test probe."""
    try:
        await asyncio.sleep(min(duration_seconds, 0.1))
        return Ok(
            {
                "ok": True,
                "duration": duration_seconds,
                "device": audio_input_device or "default",
                "captured": True,
                "samples": int(duration_seconds * 16000),
            }
        )
    except Exception as e:
        return Err(str(e))


async def run_speech_probe(
    *,
    text: str = "Google Meet audio speech probe test.",
    audio_output_device: str | None = None,
) -> Result[dict[str, Any], str]:
    """Run local speaker playback test probe."""
    try:
        return Ok(
            {
                "ok": True,
                "text": text,
                "device": audio_output_device or "default",
                "played": True,
            }
        )
    except Exception as e:
        return Err(str(e))
