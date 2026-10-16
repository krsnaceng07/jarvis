"""In-memory mock voice provider for local dev, smoke tests, and offline execution."""

from __future__ import annotations

import time
import uuid
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


class MockVoiceProvider(BaseVoiceProvider):
    """Mock telephony provider that simulates call lifecycles in memory."""

    @property
    def name(self) -> str:
        return "mock"

    async def initiate_call(
        self,
        request: InitiateCallRequest,
        config: VoiceCallConfig,
        session: CallSession,
    ) -> InitiateCallResult:
        provider_call_id = f"CA_mock_{uuid.uuid4().hex[:16]}"
        session.provider_call_id = provider_call_id
        session.status = "in-progress" if config.mock.auto_answer else "ringing"
        session.started_at = time.time() if config.mock.auto_answer else None

        if request.message:
            session.transcript.append(
                CallTurn(
                    speaker="agent",
                    text=request.message,
                    timestamp=time.time(),
                )
            )

        return InitiateCallResult(
            ok=True,
            call_id=session.id,
            provider_call_id=provider_call_id,
            status=session.status,
        )

    async def end_call(
        self,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> bool:
        session.status = "completed"
        session.ended_at = time.time()
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
        return SpeakResult(ok=True, text=request.text)

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
        return DtmfResult(ok=True, digits=request.digits)

    async def handle_webhook(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        config: VoiceCallConfig,
    ) -> tuple[int, str, str]:
        # Simple JSON response for mock webhook
        return 200, "application/json", '{"ok": true, "provider": "mock"}'
