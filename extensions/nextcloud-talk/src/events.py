"""Nextcloud Talk webhook and event parsing."""

from __future__ import annotations

from typing import Any


def parse_talk_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse incoming Nextcloud Talk webhook payload."""
    event = payload.get("event", "chat")
    target = payload.get("target", {})
    room_token = target.get("token") or payload.get("token", "")

    actor = payload.get("actor", {})
    actor_id = actor.get("id", "unknown")
    actor_name = actor.get("name", actor_id)

    object_data = payload.get("object", {})
    message_text = (
        object_data.get("name") or object_data.get("message") or payload.get("message", "")
    )
    message_id = object_data.get("id") or payload.get("id")

    return {
        "event": event,
        "room_token": room_token,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "message": message_text,
        "message_id": message_id,
        "raw": payload,
    }
