"""Buzz gossip mesh protocol message models."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BuzzMessage:
    room_id: str
    sender_id: str
    content: str
    message_id: str = field(default_factory=lambda: f"buzz_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)

    def hash(self) -> str:
        s = f"{self.room_id}:{self.sender_id}:{self.content}:{self.timestamp}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "timestamp": self.timestamp,
        }
