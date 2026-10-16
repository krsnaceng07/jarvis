"""Twilio Programmable Voice and Media Streams provider implementation."""

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


def build_twiml_response(elements: list[str]) -> str:
    """Wrap XML elements inside standard <Response>...</Response>."""
    inner = "\n  ".join(elements)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n  {inner}\n</Response>'


def twiml_say(text: str, voice: str = "alice", language: str = "en-US") -> str:
    escaped = html.escape(text)
    return f'<Say voice="{voice}" language="{language}">{escaped}</Say>'


def twiml_gather(
    action_url: str,
    method: str = "POST",
    input_types: str = "speech dtmf",
    timeout: int = 5,
    speech_timeout: str = "auto",
    say_text: str | None = None,
) -> str:
    say_elem = f"\n    {twiml_say(say_text)}" if say_text else ""
    return (
        f'<Gather action="{action_url}" method="{method}" input="{input_types}" '
        f'timeout="{timeout}" speechTimeout="{speech_timeout}">{say_elem}\n  </Gather>'
    )


def twiml_stream(stream_url: str, custom_params: dict[str, str] | None = None) -> str:
    params_xml = ""
    if custom_params:
        p_list = [
            f'<Parameter name="{html.escape(k)}" value="{html.escape(v)}"/>'
            for k, v in custom_params.items()
        ]
        params_xml = "\n    " + "\n    ".join(p_list)
    return f'<Connect>\n    <Stream url="{stream_url}">{params_xml}\n    </Stream>\n  </Connect>'


def twiml_hangup() -> str:
    return "<Hangup/>"


class TwilioVoiceProvider(BaseVoiceProvider):
    """Twilio Programmable Voice and Media Streams telephony provider."""

    @property
    def name(self) -> str:
        return "twilio"

    def _get_auth_header(self, config: VoiceCallConfig) -> str:
        # Check API key first, else Account SID + Auth Token
        if config.twilio.api_key and config.twilio.api_secret:
            creds = f"{config.twilio.api_key}:{config.twilio.api_secret}"
        else:
            creds = f"{config.twilio.account_sid}:{config.twilio.auth_token}"
        encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"

    def _get_api_base_url(self, config: VoiceCallConfig) -> str:
        reg = (config.twilio.region or "us1").lower().strip()
        if reg in ("ie1", "au1"):
            return f"https://api.{reg}.twilio.com/2010-04-01"
        return "https://api.twilio.com/2010-04-01"

    async def initiate_call(
        self,
        request: InitiateCallRequest,
        config: VoiceCallConfig,
        session: CallSession,
    ) -> InitiateCallResult:
        if not config.twilio.account_sid or not (
            config.twilio.auth_token or config.twilio.api_secret
        ):
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error="Twilio credentials missing (accountSid and authToken/apiSecret required)",
            )

        from_num = request.from_number or config.from_number
        if not from_num:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error="Twilio requires a configured fromNumber/caller ID",
            )

        # Build webhook / callback URL
        base_url = (config.public_url or "").rstrip("/")
        webhook_url = f"{base_url}/webhook/voice/twilio/answer" if base_url else ""
        status_url = f"{base_url}/webhook/voice/twilio/status?type=status" if base_url else ""

        # Prepare initial TwiML if message or stream mode
        post_data: dict[str, Any] = {
            "To": request.to_number,
            "From": from_num,
        }

        if base_url:
            post_data["Url"] = webhook_url
            post_data["StatusCallback"] = status_url
            post_data["StatusCallbackMethod"] = "POST"
            post_data["StatusCallbackEvent"] = [
                "initiated",
                "ringing",
                "answered",
                "completed",
            ]
        elif request.message:
            # Inline Twiml
            elements = [twiml_say(request.message)]
            if session.mode in ("turn", "realtime"):
                elements.append(
                    twiml_gather(action_url=webhook_url or "/webhook/voice/twilio/gather")
                )
            post_data["Twiml"] = build_twiml_response(elements)
        else:
            elements = [twiml_say("Hello from JARVIS."), twiml_hangup()]
            post_data["Twiml"] = build_twiml_response(elements)

        if request.message:
            session.transcript.append(
                CallTurn(
                    speaker="agent",
                    text=request.message,
                    timestamp=time.time(),
                )
            )

        api_base = self._get_api_base_url(config)
        url = f"{api_base}/Accounts/{config.twilio.account_sid}/Calls.json"
        body_encoded = urllib.parse.urlencode(post_data, doseq=True).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body_encoded,
            headers={
                "Authorization": self._get_auth_header(config),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                call_sid = resp_data.get("sid")
                status = resp_data.get("status", "queued")
                session.provider_call_id = call_sid
                session.status = (
                    "ringing" if status in ("queued", "initiated", "ringing") else "in-progress"
                )
                return InitiateCallResult(
                    ok=True,
                    call_id=session.id,
                    provider_call_id=call_sid,
                    status=session.status,
                )
        except Exception as ex:
            return InitiateCallResult(
                ok=False,
                call_id=session.id,
                error=f"Twilio API request failed: {ex}",
            )

    async def end_call(
        self,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> bool:
        session.status = "completed"
        session.ended_at = time.time()

        if not session.provider_call_id or not config.twilio.account_sid:
            return True

        api_base = self._get_api_base_url(config)
        url = (
            f"{api_base}/Accounts/{config.twilio.account_sid}/Calls/{session.provider_call_id}.json"
        )
        data = urllib.parse.urlencode({"Status": "completed"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": self._get_auth_header(config)},
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

        if not session.provider_call_id or not config.twilio.account_sid:
            return SpeakResult(ok=True, text=request.text)

        # Update call with new TwiML
        base_url = (config.public_url or "").rstrip("/")
        action_url = (
            f"{base_url}/webhook/voice/twilio/gather"
            if base_url
            else "/webhook/voice/twilio/gather"
        )
        elements = [
            twiml_gather(
                action_url=action_url,
                say_text=request.text,
            )
        ]
        twiml = build_twiml_response(elements)

        api_base = self._get_api_base_url(config)
        url = (
            f"{api_base}/Accounts/{config.twilio.account_sid}/Calls/{session.provider_call_id}.json"
        )
        data = urllib.parse.urlencode({"Twiml": twiml}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": self._get_auth_header(config)},
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

        if not session.provider_call_id or not config.twilio.account_sid:
            return DtmfResult(ok=True, digits=request.digits)

        # Send DTMF digits via TwiML <Play digits="...">
        elements = [f'<Play digits="{html.escape(request.digits)}"/>']
        twiml = build_twiml_response(elements)

        api_base = self._get_api_base_url(config)
        url = (
            f"{api_base}/Accounts/{config.twilio.account_sid}/Calls/{session.provider_call_id}.json"
        )
        data = urllib.parse.urlencode({"Twiml": twiml}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": self._get_auth_header(config)},
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
        # Handle status callbacks
        if "status" in path.lower() or params.get("type") == "status":
            return 200, "application/xml", build_twiml_response([])

        # Handle answer or gather
        speech_result = params.get("SpeechResult")
        digits = params.get("Digits")

        elements: list[str] = []

        base_url = (config.public_url or "").rstrip("/")
        ws_host = base_url.replace("https://", "").replace("http://", "")

        if config.realtime.enabled and ws_host:
            stream_url = f"wss://{ws_host}/voice/realtime/stream"
            elements.append(twiml_stream(stream_url))
            return 200, "application/xml", build_twiml_response(elements)

        if config.streaming.enabled and ws_host:
            stream_url = f"wss://{ws_host}{config.streaming.stream_path}"
            elements.append(twiml_stream(stream_url))
            return 200, "application/xml", build_twiml_response(elements)

        if speech_result:
            elements.append(twiml_say(f"Received speech: {speech_result}"))
        elif digits:
            elements.append(twiml_say(f"Received digits: {digits}"))
        else:
            elements.append(twiml_say("Welcome to JARVIS Voice Call."))

        action_url = (
            f"{base_url}/webhook/voice/twilio/gather"
            if base_url
            else "/webhook/voice/twilio/gather"
        )
        elements.append(twiml_gather(action_url=action_url, timeout=5))

        return 200, "application/xml", build_twiml_response(elements)
