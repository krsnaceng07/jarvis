"""Immutable ResponseRoute channel return binding.

Guarantees that responses to inbound requests return to their exact originating
transport (e.g. Telegram -> Telegram, Discord -> Discord, Desktop HUD -> Desktop HUD),
preventing remote conversations from incorrectly broadcasting to the local UI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResponseRoute:
    """Immutable routing binding for outbound responses."""

    channel: str  # e.g., "desktop", "cli", "telegram", "discord", "imessage"
    conversation_id: str
    user_id: str
    thread_id: str | None = None
    reply_to_message_id: str | None = None
    routing_epoch: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResponseRoute:
        return cls(
            channel=data["channel"],
            conversation_id=data["conversation_id"],
            user_id=data["user_id"],
            thread_id=data.get("thread_id"),
            reply_to_message_id=data.get("reply_to_message_id"),
            routing_epoch=data.get("routing_epoch", 1),
        )


__all__ = ["ResponseRoute"]
