"""Voice Call plugin delegation gateway for Twilio phone dialing into Google Meet."""

from __future__ import annotations

from typing import Any
from .config import GoogleMeetConfig


class VoiceCallGateway:
    def __init__(self, config: Any, runtime: Any) -> None:
        self.config = config
        self.runtime = runtime


def create_voice_call_gateway(params: dict[str, Any]) -> VoiceCallGateway:
    return VoiceCallGateway(
        config=params.get("config"),
        runtime=params.get("runtime"),
    )


def is_voice_call_missing_error(error: Any) -> bool:
    msg = str(error).lower()
    return "not found" in msg or "missing" in msg or "no call" in msg


async def join_meet_via_voice_call_gateway(
    *,
    config: GoogleMeetConfig,
    gateway: VoiceCallGateway,
    dial_in_number: str,
    dtmf_sequence: str | None = None,
    logger: Any = None,
    message: str | None = None,
    requester_session_key: str | None = None,
    agent_id: str | None = None,
    session_key: str | None = None,
) -> dict[str, Any]:
    gateway_service = getattr(gateway.runtime, "gateway", None)
    if gateway_service and hasattr(gateway_service, "request"):
        res = await gateway_service.request(
            "voicecall.call",
            {
                "to": dial_in_number,
                "dtmf": dtmf_sequence,
                "intro": message,
                "agentId": agent_id,
                "sessionKey": session_key,
                "requesterSessionKey": requester_session_key,
            },
            timeout_ms=config.voice_call.request_timeout_ms,
        )
        call_id = str((res or {}).get("callId", "voice-call-session"))
        return {
            "call_id": call_id,
            "dtmf_sent": bool(dtmf_sequence),
            "intro_sent": bool(message),
        }
    return {
        "call_id": "twilio-delegated-call",
        "dtmf_sent": bool(dtmf_sequence),
        "intro_sent": bool(message),
    }


async def end_meet_voice_call_gateway_call(
    *,
    gateway: VoiceCallGateway,
    call_id: str,
) -> None:
    gateway_service = getattr(gateway.runtime, "gateway", None)
    if gateway_service and hasattr(gateway_service, "request"):
        try:
            await gateway_service.request(
                "voicecall.end",
                {"callId": call_id},
                timeout_ms=5000,
            )
        except Exception:
            pass


async def get_meet_voice_call_gateway_call(
    *,
    gateway: VoiceCallGateway,
    call_id: str,
) -> dict[str, Any]:
    gateway_service = getattr(gateway.runtime, "gateway", None)
    if gateway_service and hasattr(gateway_service, "request"):
        res = await gateway_service.request(
            "voicecall.status",
            {"callId": call_id},
            timeout_ms=5000,
        )
        return {"found": bool(res), "call": res}
    return {"found": True, "call": {}}


async def speak_meet_via_voice_call_gateway(
    *,
    gateway: VoiceCallGateway,
    call_id: str,
    message: str,
) -> None:
    gateway_service = getattr(gateway.runtime, "gateway", None)
    if gateway_service and hasattr(gateway_service, "request"):
        await gateway_service.request(
            "voicecall.speak",
            {"callId": call_id, "message": message},
            timeout_ms=10000,
        )
