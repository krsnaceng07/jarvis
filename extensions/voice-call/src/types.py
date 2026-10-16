"""Core domain types and data models for the Voice Call plugin."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

CallDirection = Literal["inbound", "outbound"]
CallStatusKind = Literal[
    "initiated",
    "ringing",
    "in-progress",
    "completed",
    "busy",
    "failed",
    "no-answer",
    "canceled",
]


@dataclass(slots=True)
class CallTurn:
    speaker: Literal["user", "agent", "system"]
    text: str
    timestamp: float = field(default_factory=time.time)
    confidence: float | None = None
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass(slots=True)
class CallSession:
    id: str
    provider: str
    from_number: str
    to_number: str
    direction: CallDirection
    status: CallStatusKind = "initiated"
    provider_call_id: str | None = None
    mode: str = "turn"
    agent_id: str = "main"
    transcript: list[CallTurn] = field(default_factory=list)
    dtmf_log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    answered_at: float | None = None
    ended_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stream_sid: str | None = None
    conversation_state: str = "idle"  # "idle", "listening", "speaking"
    last_activity_time: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.status in ("initiated", "ringing", "in-progress")

    @property
    def duration_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.ended_at or time.time()
        return max(0.0, end - self.started_at)


@dataclass(slots=True)
class CallStatus:
    session_id: str
    active: bool
    status: CallStatusKind
    direction: CallDirection
    provider: str
    from_number: str
    to_number: str
    mode: str
    duration_seconds: float
    turn_count: int
    last_speech: str | None = None
    agent_id: str = "main"


@dataclass(slots=True)
class InitiateCallRequest:
    to_number: str
    from_number: str | None = None
    message: str | None = None
    mode: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InitiateCallResult:
    ok: bool
    call_id: str | None = None
    provider_call_id: str | None = None
    status: str | None = None
    error: str | None = None


@dataclass(slots=True)
class SpeakRequest:
    call_id: str
    text: str
    voice: str | None = None
    model: str | None = None
    interrupt: bool = False


@dataclass(slots=True)
class SpeakResult:
    ok: bool
    text: str
    error: str | None = None


@dataclass(slots=True)
class DtmfRequest:
    call_id: str
    digits: str


@dataclass(slots=True)
class DtmfResult:
    ok: bool
    digits: str
    error: str | None = None
