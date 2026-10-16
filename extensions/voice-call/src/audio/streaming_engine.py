"""Streaming speech-to-text transcription engine (OpenAI, xAI, Deepgram, ElevenLabs, Mistral)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import VoiceCallStreamingConfig
from ..types import CallSession, CallTurn

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamingTranscriberState:
    session_id: str
    provider: str
    model: str
    language: str
    started_at: float
    is_ready: bool = False
    buffer: bytearray = field(default_factory=bytearray)
    queued_audio_chunks: list[bytes] = field(default_factory=list)
    greeting_sent: bool = False
    options: dict[str, Any] = field(default_factory=dict)


class StreamingTranscriptionEngine:
    """Manages streaming speech transcription over carrier media streams (Twilio Media Streams)."""

    def __init__(self) -> None:
        self._active_transcribers: dict[str, StreamingTranscriberState] = {}

    def resolve_provider_defaults(
        self,
        config: VoiceCallStreamingConfig,
    ) -> tuple[str, str, str, dict[str, Any]]:
        """Resolve model, language, and options for streaming provider (OpenAI, xAI, etc.)."""
        prov = config.provider.lower().strip()
        provider_cfg = config.providers.get(prov, {})

        if prov == "xai":
            resolved_prov = "xai"
            model = config.model or provider_cfg.get("model") or "stt-1"
            language = config.language or provider_cfg.get("language") or "en"
            options = {
                "endpoint": provider_cfg.get("endpoint", "wss://api.x.ai/v1/stt"),
                "encoding": provider_cfg.get("encoding", "mulaw"),
                "sampleRate": int(provider_cfg.get("sampleRate", 8000)),
                "endpointingMs": int(provider_cfg.get("endpointingMs", 800)),
                "interimResults": bool(provider_cfg.get("interimResults", True)),
                "apiKey": provider_cfg.get("apiKey"),
            }
        elif prov == "openai":
            resolved_prov = "openai"
            model = config.model or provider_cfg.get("model") or "gpt-4o-transcribe"
            language = config.language or provider_cfg.get("language") or "en"
            options = {
                "silenceDurationMs": int(provider_cfg.get("silenceDurationMs", 800)),
                "vadThreshold": float(provider_cfg.get("vadThreshold", 0.5)),
                "apiKey": provider_cfg.get("apiKey"),
            }
        else:
            resolved_prov = prov
            model = config.model or provider_cfg.get("model") or "default"
            language = config.language or provider_cfg.get("language") or "en"
            options = dict(provider_cfg)

        return resolved_prov, model, language, options

    async def start_stream(
        self,
        session: CallSession,
        config: VoiceCallStreamingConfig,
    ) -> StreamingTranscriberState:
        """Start streaming transcription for a call session, queueing media until ready."""
        prov, model, lang, opts = self.resolve_provider_defaults(config)
        state = StreamingTranscriberState(
            session_id=session.id,
            provider=prov,
            model=model,
            language=lang,
            started_at=time.time(),
            is_ready=False,
            options=opts,
        )
        self._active_transcribers[session.id] = state
        return state

    def mark_ready(self, session_id: str) -> list[bytes]:
        """Mark streaming connection ready and return queued inbound audio chunks to process."""
        state = self._active_transcribers.get(session_id)
        if state:
            state.is_ready = True
            queued = list(state.queued_audio_chunks)
            state.queued_audio_chunks.clear()
            return queued
        return []

    def is_ready(self, session_id: str) -> bool:
        """Check if streaming transcriber is connected and ready for audio."""
        state = self._active_transcribers.get(session_id)
        return bool(state and state.is_ready)

    async def ingest_audio(
        self,
        session: CallSession,
        audio_chunk: bytes,
    ) -> None:
        """Accumulate or queue audio stream data for transcription."""
        state = self._active_transcribers.get(session.id)
        if state is not None:
            if not state.is_ready:
                state.queued_audio_chunks.append(audio_chunk)
            state.buffer.extend(audio_chunk)

    async def emit_transcript(
        self,
        session: CallSession,
        text: str,
        is_final: bool = True,
    ) -> CallTurn:
        """Append transcribed text to call transcript."""
        turn = CallTurn(
            speaker="user",
            text=text.strip(),
            timestamp=time.time(),
        )
        if is_final and text.strip():
            session.transcript.append(turn)
            session.last_activity_time = time.time()
        return turn

    async def end_stream(self, session_id: str) -> None:
        """Close streaming transcriber."""
        self._active_transcribers.pop(session_id, None)
