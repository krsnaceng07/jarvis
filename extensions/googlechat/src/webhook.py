"""Webhook verification and payload processing for Google Chat events."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.extensions.googlechat")


def parse_google_chat_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract standard normalized message fields from Google Chat incoming event."""
    event_type = payload.get("type", "UNKNOWN")
    space = payload.get("space", {})
    space_name = space.get("name", "")
    space_type = space.get("type", "ROOM")  # DM or ROOM

    message = payload.get("message", {})
    text = message.get("text", "")
    sender = message.get("sender", {}).get("displayName") or message.get("sender", {}).get(
        "name", "unknown"
    )
    thread_name = message.get("thread", {}).get("name", "")

    return {
        "event_type": event_type,
        "space_name": space_name,
        "space_type": space_type,
        "sender": sender,
        "text": text,
        "thread_name": thread_name,
        "raw": payload,
    }
