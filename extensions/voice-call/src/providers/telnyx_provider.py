"""Telnyx Call Control v2 telephony provider implementation."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from ..config import VoiceCallConfig
from ..types import (
    CallSession,
    CallTurn,
    DtmfRequest,
    DtmfResult,
    InitiateCallRequest,
    InitiateCallResult,
    SpeakRequest,
    SpeakResult,
)
from .base import BaseVoiceProvider


class TelnyxVoiceProvider(BaseVoiceProvider):
    """Telnyx Call Control v2 telephony provider."""

    @property
    def name(self) -> str:
        return "telnyx"

    def _get_headers(self, config: VoiceCallConfig) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {config.telnyx.api_key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def initiate_call(
        self,
        request: InitiateCallRequest,
        config: VoiceCallConfig,
        session: CallSession,
    ) -> InitiateCallResult:
        if not config.telnyx.api_key or not config.telnyx.connection_id:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error="Telnyx credentials missing (apiKey and connectionId required)",
            )

        from_num = request.from_number or config.from_number
        if not from_num:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error="Telnyx requires a configured fromNumber/caller ID",
            )

        base_url = (config.public_url or "").rstrip("/")
        webhook_url = f"{base_url}/webhook/voice/telnyx" if base_url else None

        post_data: dict[str, Any] = {
            "to": request.to_number,
            "from": from_num,
            "connection_id": config.telnyx.connection_id,
        }
        if webhook_url:
            post_data["webhook_url"] = webhook_url

        if request.message:
            session.transcript.append(
                CallTurn(
                    speaker="agent",
                    text=request.message,
                    timestamp=time.time(),
                )
            )

        url = "https://api.telnyx.com/v2/calls"
        body_bytes = json.dumps(post_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._get_headers(config),
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                call_control_id = resp_json.get("data", {}).get("call_control_id")
                session.provider_call_id = call_control_id
                session.status = "ringing"
                return InitiateCallResult(
                    ok=True,
                    call_id=session.id,
                    provider_call_id=call_control_id,
                    status=session.status,
                )
        except Exception as ex:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error=f"Telnyx API call initiation failed: {ex}",
            )

    async def end_call(
        self,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> bool:
        session.status = "completed"
        session.ended_at = time.time()

        if not session.provider_call_id or not config.telnyx.api_key:
            return True

        url = f"https://api.telnyx.com/v2/calls/{session.provider_call_id}/actions/hangup"
        body_bytes = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._get_headers(config),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as _:
                return True
        except Exception:
            return True

    async def speak(
        self,
        request: SpeakRequest,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> SpeakResult:
        if not session.is_active:
            return SpeakResult(ok=False, text=request.text, error="Call is not active")

        session.transcript.append(
            CallTurn(
                speaker="agent",
                text=request.text,
                timestamp=time.time(),
            )
        )
        session.last_activity_time = time.time()

        if not session.provider_call_id or not config.telnyx.api_key:
            return SpeakResult(ok=True, text=request.text)

        url = f"https://api.telnyx.com/v2/calls/{session.provider_call_id}/actions/speak"
        post_data = {
            "payload": request.text,
            "voice": request.voice or "female",
            "language": "en-US",
        }
        body_bytes = json.dumps(post_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._get_headers(config),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as _:
                return SpeakResult(ok=True, text=request.text)
        except Exception as ex:
            return SpeakResult(ok=False, text=request.text, error=str(ex))

    async def send_dtmf(
        self,
        request: DtmfRequest,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> DtmfResult:
        if not session.is_active:
            return DtmfResult(ok=False, digits=request.digits, error="Call is not active")

        session.dtmf_log.append(request.digits)
        session.transcript.append(
            CallTurn(
                speaker="system",
                text=f"DTMF sent: {request.digits}",
                timestamp=time.time(),
            )
        )
        session.last_activity_time = time.time()

        if not session.provider_call_id or not config.telnyx.api_key:
            return DtmfResult(ok=True, digits=request.digits)

        url = f"https://api.telnyx.com/v2/calls/{session.provider_call_id}/actions/send_dtmf"
        post_data = {"digits": request.digits}
        body_bytes = json.dumps(post_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._get_headers(config),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as _:
                return DtmfResult(ok=True, digits=request.digits)
        except Exception as ex:
            return DtmfResult(ok=False, digits=request.digits, error=str(ex))

    async def handle_webhook(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        config: VoiceCallConfig,
    ) -> tuple[int, str, str]:
        event_data = params.get("data", {})
        event_type = event_data.get("event_type", "")
        return 200, "application/json", json.dumps({"status": "received", "event": event_type})
