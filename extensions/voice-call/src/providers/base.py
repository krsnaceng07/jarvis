"""Abstract base provider class for telephony integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..config import VoiceCallConfig
from ..types import (
    CallSession,
    DtmfRequest,
    DtmfResult,
    InitiateCallRequest,
    InitiateCallResult,
    SpeakRequest,
    SpeakResult,
)


class BaseVoiceProvider(ABC):
    """Abstract interface that every voice provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'mock', 'twilio', 'telnyx', 'plivo')."""
        ...

    @abstractmethod
    async def initiate_call(
        self,
        request: InitiateCallRequest,
        config: VoiceCallConfig,
        session: CallSession,
    ) -> InitiateCallResult:
        """Place an outbound telephone call."""
        ...

    @abstractmethod
    async def end_call(
        self,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> bool:
        """Terminate an active call."""
        ...

    @abstractmethod
    async def speak(
        self,
        request: SpeakRequest,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> SpeakResult:
        """Speak a message to the caller/callee during a live call."""
        ...

    @abstractmethod
    async def send_dtmf(
        self,
        request: DtmfRequest,
        session: CallSession,
        config: VoiceCallConfig,
    ) -> DtmfResult:
        """Transmit DTMF tones into the active call."""
        ...

    @abstractmethod
    async def handle_webhook(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        config: VoiceCallConfig,
    ) -> tuple[int, str, str]:
        """Process incoming provider webhook. Returns (status_code, content_type, body)."""
        ...
