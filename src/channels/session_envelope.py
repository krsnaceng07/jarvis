"""Session envelope — mirrors OpenClaw ``src/channels/session-envelope.ts``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionEnvelope:
    """Canonical wrapper for an inbound channel message passing through routing."""

    channel_id: str
    sender_id: str
    content: str
    sender_username: str | None = None
    thread_id: str | None = None
    account_id: str | None = None
    model_override: str | None = None
    allowed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        """Derive session key for storage / runner tracking."""
        base = f"{self.channel_id}:{self.sender_id}"
        if self.thread_id:
            return f"{base}:{self.thread_id}"
        return base


__all__ = ["SessionEnvelope"]
