"""Plivo Voice API and XML transfer provider implementation."""

from __future__ import annotations

import base64
import html
import json
import time
import urllib.parse
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


def build_plivo_xml(elements: list[str]) -> str:
    inner = "\n  ".join(elements)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n  {inner}\n</Response>'


class PlivoVoiceProvider(BaseVoiceProvider):
    """Plivo Voice API and XML transfer telephony provider."""

    @property
    def name(self) -> str:
        return "plivo"

    def _get_auth_header(self, config: VoiceCallConfig) -> str:
        creds = f"{config.plivo.auth_id}:{config.plivo.auth_token}"
        encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"

    async def initiate_call(
        self,
        request: InitiateCallRequest,
        config: VoiceCallConfig,
        session: CallSession,
    ) -> InitiateCallResult:
        if not config.plivo.auth_id or not config.plivo.auth_token:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error="Plivo credentials missing (authId and authToken required)",
            )

        from_num = request.from_number or config.from_number
        if not from_num:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error="Plivo requires a configured fromNumber/caller ID",
            )

        base_url = (config.public_url or "").rstrip("/")
        answer_url = f"{base_url}/webhook/voice/plivo/answer" if base_url else "https://plivo.com"

        post_data = {
            "to": request.to_number,
            "from": from_num,
            "answer_url": answer_url,
            "answer_method": "POST",
        }

        if request.message:
            session.transcript.append(
                CallTurn(
                    speaker="agent",
                    text=request.message,
                    timestamp=time.time(),
                )
            )

        url = f"https://api.plivo.com/v1/Account/{config.plivo.auth_id}/Call/"
        body_bytes = json.dumps(post_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Authorization": self._get_auth_header(config),
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                request_uuid = resp_data.get("request_uuid") or resp_data.get("api_id")
                session.provider_call_id = request_uuid
                session.status = "ringing"
                return InitiateCallResult(
                    ok=True,
                    call_id=session.id,
                    provider_call_id=request_uuid,
                    status=session.status,
                )
        except Exception as ex:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error=f"Plivo API call initiation failed: {ex}",
            )

    async def end_call(
        self,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> bool:
        session.status = "completed"
        session.ended_at = time.time()

        if not session.provider_call_id or not config.plivo.auth_id:
            return True

        url = f"https://api.plivo.com/v1/Account/{config.plivo.auth_id}/Call/{session.provider_call_id}/"
        req = urllib.request.Request(
            url,
            headers={"Authorization": self._get_auth_header(config)},
            method="DELETE",
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

        if not session.provider_call_id or not config.plivo.auth_id:
            return SpeakResult(ok=True, text=request.text)

        url = f"https://api.plivo.com/v1/Account/{config.plivo.auth_id}/Call/{session.provider_call_id}/Speak/"
        post_data = {"text": request.text, "voice": request.voice or "WOMAN"}
        body_bytes = json.dumps(post_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Authorization": self._get_auth_header(config),
                "Content-Type": "application/json",
            },
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

        if not session.provider_call_id or not config.plivo.auth_id:
            return DtmfResult(ok=True, digits=request.digits)

        url = f"https://api.plivo.com/v1/Account/{config.plivo.auth_id}/Call/{session.provider_call_id}/DTMF/"
        post_data = {"digits": request.digits}
        body_bytes = json.dumps(post_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Authorization": self._get_auth_header(config),
                "Content-Type": "application/json",
            },
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
        speech = params.get("Speech")
        digits = params.get("Digits")

        elements: list[str] = []
        if speech:
            elements.append(f"<Speak>Heard: {html.escape(str(speech))}</Speak>")
        elif digits:
            elements.append(f"<Speak>Digits: {html.escape(str(digits))}</Speak>")
        else:
            elements.append("<Speak>Connected to JARVIS Voice.</Speak>")

        base_url = (config.public_url or "").rstrip("/")
        action_url = (
            f"{base_url}/webhook/voice/plivo/input" if base_url else "/webhook/voice/plivo/input"
        )
        elements.append(
            f'<GetInput action="{action_url}" method="POST" inputType="speech dtmf" executionTimeout="5"/>'
        )

        return 200, "application/xml", build_plivo_xml(elements)
