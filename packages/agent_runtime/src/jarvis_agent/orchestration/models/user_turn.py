"""Channel-neutral normalized UserTurn envelope.

Every channel input (Desktop HUD, CLI, Telegram, Discord, etc.) normalizes into
this envelope before reaching stage detection, task resolution, or planning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any

from jarvis_agent.orchestration.models.response_route import ResponseRoute


@dataclass(frozen=True, slots=True)
class Attachment:
    """Metadata and content reference for input attachments."""

    attachment_id: str
    filename: str
    media_type: str
    size_bytes: int
    sha256_digest: str
    uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class UserTurn:
    """Normalized, channel-neutral turn envelope."""

    turn_id: str
    request_id: str
    session_id: str
    conversation_id: str
    user_id: str
    timestamp_utc: str
    raw_text: str
    clean_text: str
    response_route: ResponseRoute
    attachments: list[Attachment] = field(default_factory=list)
    reply_context: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["response_route"] = self.response_route.to_dict()
        d["attachments"] = [a.to_dict() for a in self.attachments]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserTurn:
        route_raw = data.get("response_route", {})
        route = ResponseRoute.from_dict(route_raw) if isinstance(route_raw, dict) else route_raw
        attachments = [
            Attachment(**a) if isinstance(a, dict) else a for a in data.get("attachments", [])
        ]
        return cls(
            turn_id=data["turn_id"],
            request_id=data.get("request_id", data["turn_id"]),
            session_id=data["session_id"],
            conversation_id=data["conversation_id"],
            user_id=data["user_id"],
            timestamp_utc=data.get(
                "timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            raw_text=data["raw_text"],
            clean_text=data.get("clean_text", data["raw_text"].strip()),
            response_route=route,
            attachments=attachments,
            reply_context=data.get("reply_context", {}),
            correlation_id=data.get("correlation_id", ""),
        )


__all__ = ["Attachment", "UserTurn"]
