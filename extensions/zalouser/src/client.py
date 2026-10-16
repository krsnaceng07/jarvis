"""Zalo Personal Account Client."""

from __future__ import annotations

import logging
from typing import Any

from .session import ZaloUserSession

logger = logging.getLogger("jarvis.extensions.zalouser")


class ZaloUserClient:
    """Client for Zalo personal user interactions."""

    def __init__(self, session: ZaloUserSession) -> None:
        self.session = session

    def send_direct_message(self, recipient_id: str, text: str) -> dict[str, Any]:
        """Send a direct message to a user or group."""
        if not self.session.is_authenticated():
            return {"error": "unauthenticated"}
        # Format simulated message payload
        return {
            "status": 0,
            "msg": "success",
            "data": {
                "to": recipient_id,
                "text": text,
                "msg_id": f"zmsg_{hash(text) & 0xFFFFFFFF:x}",
            },
        }

    def add_reaction(self, msg_id: str, emoji: str) -> dict[str, Any]:
        """React to a message with an emoji."""
        if not self.session.is_authenticated():
            return {"error": "unauthenticated"}
        return {"status": 0, "msg": "success", "msg_id": msg_id, "emoji": emoji}
