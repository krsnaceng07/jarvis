"""Central runtime coordinator and session manager for Voice Call."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any


from jarvis_sdk import Err, Ok, Result

from .audio.realtime_engine import RealtimeVoiceEngine
from .audio.streaming_engine import StreamingTranscriptionEngine
from .audio.tts_engine import TTSEngine
from .config import VoiceCallConfig
from .phone_utils import normalize_e164_phone_number
from .providers.base import BaseVoiceProvider
from .providers.mock_provider import MockVoiceProvider
from .providers.plivo_provider import PlivoVoiceProvider
from .providers.telnyx_provider import TelnyxVoiceProvider
from .providers.twilio_provider import TwilioVoiceProvider
from .reaper import StaleCallReaper
from .spoken_output import append_spoken_output_contract, extract_spoken_output_text
from .types import (
    CallSession,
    CallStatus,
    DtmfRequest,
    DtmfResult,
    InitiateCallRequest,
    InitiateCallResult,
    SpeakRequest,
    SpeakResult,
)

logger = logging.getLogger(__name__)


class VoiceCallRuntime:
    """Manages active call sessions, provider dispatch, lifecycle events, and disconnect grace."""

    def __init__(self, config: VoiceCallConfig | None = None) -> None:
        self.config = config or VoiceCallConfig()
        self._sessions: dict[str, CallSession] = {}
        self._phone_to_session: dict[str, str] = {}
        self._providers: dict[str, BaseVoiceProvider] = {
            "mock": MockVoiceProvider(),
            "twilio": TwilioVoiceProvider(),
            "telnyx": TelnyxVoiceProvider(),
            "plivo": PlivoVoiceProvider(),
        }
        self.tts_engine = TTSEngine(self.config.tts)
        self.realtime_engine = RealtimeVoiceEngine()
        self.streaming_engine = StreamingTranscriptionEngine()
        self.reaper = StaleCallReaper(
            timeout_seconds=self.config.stale_call_reaper_seconds,
            max_duration_seconds=self.config.max_duration_seconds,
        )
        self._disconnect_tasks: dict[str, asyncio.Task[None]] = {}
        self._active_generation_ids: dict[str, str] = {}

    def get_provider(self, name: str | None = None) -> BaseVoiceProvider:
        prov_name = (name or self.config.provider or "twilio").lower().strip()
        return self._providers.get(prov_name, self._providers["mock"])

    def register_provider(self, provider: BaseVoiceProvider) -> None:
        self._providers[provider.name.lower()] = provider

    def find_session(
        self,
        session_id: str | None = None,
        phone_number: str | None = None,
    ) -> CallSession | None:
        """Find an active or matching call session."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        if phone_number:
            try:
                norm_phone = normalize_e164_phone_number(phone_number)
            except ValueError:
                norm_phone = phone_number.strip()
            sid = self._phone_to_session.get(norm_phone)
            if sid and sid in self._sessions:
                return self._sessions[sid]

        # Return most recently active session if no filter
        if not session_id and not phone_number and self._sessions:
            active = [s for s in self._sessions.values() if s.is_active]
            if active:
                return sorted(active, key=lambda s: s.last_activity_time, reverse=True)[0]
            return sorted(
                self._sessions.values(), key=lambda s: s.last_activity_time, reverse=True
            )[0]

        return None

    async def initiate(
        self,
        to_number: str,
        from_number: str | None = None,
        message: str | None = None,
        mode: str | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[InitiateCallResult, str]:
        """Initiate an outbound telephone call."""
        try:
            norm_to = normalize_e164_phone_number(to_number)
        except ValueError as ex:
            return Err(f"Invalid destination phone number: {ex}")

        norm_from = from_number
        if from_number:
            try:
                norm_from = normalize_e164_phone_number(from_number)
            except ValueError as ex:
                return Err(f"Invalid caller ID number: {ex}")

        # Check session scoping (per-phone vs per-call)
        if self.config.session_scope == "per-phone" and norm_to in self._phone_to_session:
            existing_id = self._phone_to_session[norm_to]
            existing_sess = self._sessions.get(existing_id)
            if existing_sess and existing_sess.is_active:
                return Ok(
                    InitiateCallResult(
                        ok=True,
                        call_id=existing_sess.id,
                        provider_call_id=existing_sess.provider_call_id,
                        status=existing_sess.status,
                    )
                )

        session_id = f"call_{uuid.uuid4().hex[:12]}"
        req_mode = mode or self.config.mode or "turn"
        req_agent = agent_id or self.config.agent_id or "main"
        sess_meta = dict(metadata or {})
        from .session_keys import resolve_voice_session_key

        sess_meta["session_key"] = resolve_voice_session_key(
            scope=self.config.session_scope,
            agent_id=req_agent,
            phone_number=norm_to,
            call_id=session_id,
        )

        session = CallSession(
            id=session_id,
            provider=self.config.provider,
            from_number=norm_from or self.config.from_number or "+15555550100",
            to_number=norm_to,
            direction="outbound",
            status="initiated",
            mode=req_mode,
            agent_id=req_agent,
            metadata=sess_meta,
        )

        self._sessions[session_id] = session
        self._phone_to_session[norm_to] = session_id

        provider = self.get_provider()
        req = InitiateCallRequest(
            to_number=norm_to,
            from_number=norm_from,
            message=message,
            mode=req_mode,
            agent_id=req_agent,
            metadata=metadata or {},
        )

        res = await provider.initiate_call(req, self.config, session)
        if not res.ok:
            session.status = "failed"
            return Err(res.error or "Failed to initiate call")

        return Ok(res)

    async def speak(
        self,
        text: str,
        session_id: str | None = None,
        phone_number: str | None = None,
    ) -> Result[SpeakResult, str]:
        """Speak a message into an active call."""
        session = self.find_session(session_id, phone_number)
        if not session:
            return Err("No matching active call session found")

        provider = self.get_provider(session.provider)
        req = SpeakRequest(call_id=session.id, text=text)
        res = await provider.speak(req, session, self.config)
        if not res.ok:
            return Err(res.error or "Failed to speak message")
        return Ok(res)

    async def send_dtmf(
        self,
        digits: str,
        session_id: str | None = None,
        phone_number: str | None = None,
    ) -> Result[DtmfResult, str]:
        """Send DTMF tones into an active call."""
        session = self.find_session(session_id, phone_number)
        if not session:
            return Err("No matching active call session found")

        provider = self.get_provider(session.provider)
        req = DtmfRequest(call_id=session.id, digits=digits)
        res = await provider.send_dtmf(req, session, self.config)
        if not res.ok:
            return Err(res.error or "Failed to transmit DTMF tones")
        return Ok(res)

    async def end_call(
        self,
        session_id: str | None = None,
        phone_number: str | None = None,
    ) -> Result[bool, str]:
        """Terminate an active call."""
        session = self.find_session(session_id, phone_number)
        if not session:
            return Err("No matching call session found")

        provider = self.get_provider(session.provider)
        ok = await provider.end_call(session, self.config)
        return Ok(ok)

    async def get_status(
        self,
        session_id: str | None = None,
        phone_number: str | None = None,
    ) -> Result[dict[str, Any], str]:
        """Inspect call session status."""
        session = self.find_session(session_id, phone_number)
        if not session:
            return Ok({"active": False, "session": None})

        last_speech = session.transcript[-1].text if session.transcript else None
        status = CallStatus(
            session_id=session.id,
            active=session.is_active,
            status=session.status,
            direction=session.direction,
            provider=session.provider,
            from_number=session.from_number,
            to_number=session.to_number,
            mode=session.mode,
            duration_seconds=session.duration_seconds,
            turn_count=len(session.transcript),
            last_speech=last_speech,
            agent_id=session.agent_id,
        )

        return Ok(
            {
                "active": status.active,
                "session": {
                    "id": status.session_id,
                    "status": status.status,
                    "direction": status.direction,
                    "provider": status.provider,
                    "from": status.from_number,
                    "to": status.to_number,
                    "mode": status.mode,
                    "durationSeconds": status.duration_seconds,
                    "turnCount": status.turn_count,
                    "lastSpeech": status.last_speech,
                    "agentId": status.agent_id,
                    "transcript": [
                        {"speaker": t.speaker, "text": t.text, "timestamp": t.timestamp}
                        for t in session.transcript
                    ],
                },
            }
        )

    async def smoke_test(
        self,
        to_number: str | None = None,
        live: bool = False,
    ) -> Result[dict[str, Any], str]:
        """Run a voice call smoke test."""
        target = to_number or self.config.to_number or "+15555550123"
        try:
            norm_target = normalize_e164_phone_number(target)
        except ValueError as ex:
            return Err(f"Invalid smoke test target number: {ex}")

        if not live:
            # Dry run
            return Ok(
                {
                    "dryRun": True,
                    "target": norm_target,
                    "provider": self.config.provider,
                    "status": "ready",
                    "message": f"Smoke test ready (dry run). Pass live=True or --yes to place call to {norm_target}.",
                }
            )

        # Live call placement
        init_res = await self.initiate(
            to_number=norm_target,
            message="This is a JARVIS Voice Call smoke test.",
        )
        if not init_res.is_ok:
            return Err(f"Smoke test live call failed: {init_res.unwrap_err()}")

        res_val = init_res.unwrap()
        return Ok(
            {
                "dryRun": False,
                "target": norm_target,
                "provider": self.config.provider,
                "status": res_val.status,
                "callId": res_val.call_id,
                "providerCallId": res_val.provider_call_id,
            }
        )

    def handle_stream_disconnect(
        self,
        session_id: str,
        grace_seconds: float | None = None,
    ) -> None:
        """Wait for disconnect grace period (default 2.0s) before terminating the call on media stream drop."""
        grace = grace_seconds if grace_seconds is not None else self.config.disconnect_grace_seconds

        # Close realtime bridge/session resources immediately
        if session_id in self.realtime_engine._active_sessions:
            asyncio.create_task(
                self.realtime_engine.end_session(session_id, cause="stream-disconnect")
            )

        async def _disconnect_grace_timer() -> None:
            try:
                await asyncio.sleep(grace)
                session = self._sessions.get(session_id)
                if session and session.is_active:
                    logger.warning(
                        "Stream disconnect grace period (%ss) expired for %s. Ending call.",
                        grace,
                        session_id,
                    )
                    await self.end_call(session_id=session_id)
            except asyncio.CancelledError:
                logger.info(
                    "Stream disconnect grace timer cancelled for %s (stream reconnected).",
                    session_id,
                )

        task = asyncio.create_task(_disconnect_grace_timer())
        self._disconnect_tasks[session_id] = task

    def handle_stream_connect(self, session_id: str) -> None:
        """Cancel pending disconnect grace timer when media stream reconnects."""
        task = self._disconnect_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def handle_caller_speech_start(self, session_id: str) -> None:
        """Handle caller speech start / barge-in by clearing pending playback and invalidating in-flight replies."""
        self.tts_engine.clear_pending_queue(session_id, reason="caller-barge-in")
        # Invalidate current generation id to discard in-flight model response
        self._active_generation_ids[session_id] = uuid.uuid4().hex

    def prepare_agent_prompt(self, system_prompt: str | None) -> str:
        """Append the strict spoken output JSON contract to the system prompt."""
        return append_spoken_output_contract(system_prompt or self.config.response_system_prompt)

    def extract_reply(self, raw_model_response: str | dict[str, Any] | None) -> str:
        """Defensively extract spoken reply text from model output."""
        return extract_spoken_output_text(raw_model_response)
