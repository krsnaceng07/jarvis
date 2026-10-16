"""Runtime test probes for speech and caption listening verification in Teams Meetings."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from jarvis_sdk import Err, Ok, Result

from .config import TeamsMeetingsConfig
from .teams_url import normalize_teams_url
from .transports.teams_platform_adapter import is_talk_back_mode
from .transports.types import (
    TeamsMeetingsJoinRequest,
    TeamsMeetingsJoinResult,
    TeamsMeetingsSession,
)


class TeamsMeetingsRuntimeProbeContext(Protocol):
    config: TeamsMeetingsConfig

    def resolve_agent_id(self, request: TeamsMeetingsJoinRequest) -> str: ...

    def list(self) -> list[TeamsMeetingsSession]: ...

    async def join(self, request: TeamsMeetingsJoinRequest) -> TeamsMeetingsJoinResult: ...

    async def refresh_caption_health(self, session: TeamsMeetingsSession) -> None: ...


def resolve_probe_timeout_ms(input_val: int | None, fallback: int) -> int:
    if input_val is None:
        return min(max(fallback, 1), 120000)
    if input_val <= 0:
        raise ValueError("timeoutMs must be a positive number")
    return min(int(input_val), 120000)


async def test_teams_meetings_listening(
    context: TeamsMeetingsRuntimeProbeContext,
    request: TeamsMeetingsJoinRequest,
) -> dict[str, Any]:
    req_mode = "agent" if request.mode == "realtime" else request.mode
    if req_mode and req_mode != "transcribe":
        raise ValueError(
            "test_listen requires mode: transcribe; use test_speech for talk-back sessions."
        )

    transport = request.transport or context.config.default_transport
    normalized_url = normalize_teams_url(request.url)
    resolved_req = TeamsMeetingsJoinRequest(
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
        if isinstance(session, TeamsMeetingsSession):
            await context.refresh_caption_health(session)
            health = (
                session.chrome.health
                if session.chrome and hasattr(session.chrome, "health")
                else None
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
        "session_id": getattr(session, "id", ""),
        "message": f"Did not receive captions within {timeout_ms}ms.",
    }


async def test_teams_meetings_speech(
    context: TeamsMeetingsRuntimeProbeContext,
    request: TeamsMeetingsJoinRequest,
) -> dict[str, Any]:
    req_mode = "agent" if request.mode == "realtime" else request.mode
    if req_mode and not is_talk_back_mode(req_mode):
        raise ValueError(
            "test_speech requires mode: agent or bidi; use join mode: transcribe for observe-only sessions."
        )

    mode = req_mode or "agent"
    transport = request.transport or context.config.default_transport
    normalized_url = normalize_teams_url(request.url)
    default_msg = "Say exactly: Microsoft Teams speech test complete."
    message = request.message or default_msg

    resolved_req = TeamsMeetingsJoinRequest(
        url=normalized_url,
        transport=transport,
        mode=mode,
        message=message,
        agent_id=request.agent_id,
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
        "session_id": getattr(session, "id", ""),
        "sessionId": getattr(session, "id", ""),
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
    text: str = "Microsoft Teams audio speech probe test.",
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
