"""LINE Webhook event parsing and modeling."""

from __future__ import annotations

from typing import Any


def parse_line_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse events array from LINE webhook JSON body."""
    raw_events = payload.get("events", [])
    parsed: list[dict[str, Any]] = []

    for ev in raw_events:
        ev_type = ev.get("type", "unknown")
        reply_token = ev.get("replyToken")
        source = ev.get("source", {})
        source_type = source.get("type", "user")
        user_id = source.get("userId") or source.get("groupId") or source.get("roomId")

        message = ev.get("message", {})
        msg_type = message.get("type", "text")
        text = message.get("text", "")

        parsed.append(
            {
                "type": ev_type,
                "reply_token": reply_token,
                "source_type": source_type,
                "user_id": user_id,
                "message_type": msg_type,
                "text": text,
                "timestamp": ev.get("timestamp"),
                "raw": ev,
            }
        )

    return parsed
