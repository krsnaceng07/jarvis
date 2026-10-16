"""Synology Chat Incoming Webhook client."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("jarvis.extensions.synology_chat")


class SynologyChatClient:
    """Client for Synology Chat incoming webhooks."""

    def __init__(self, incoming_url: str) -> None:
        self.incoming_url = incoming_url

    def send_message(self, text: str, user_ids: list[int] | None = None) -> dict[str, Any]:
        """Send message payload to Synology Chat incoming webhook."""
        if not self.incoming_url:
            return {"error": "no_incoming_url"}

        payload: dict[str, Any] = {"text": text}
        if user_ids:
            payload["user_ids"] = user_ids

        # Synology Chat expects form-urlencoded payload={"text": "..."}
        form_data = urlencode({"payload": json.dumps(payload)}).encode("utf-8")
        req = Request(
            self.incoming_url,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"success": True}
        except Exception as e:
            logger.warning(f"Synology Chat webhook failed: {e}")
            return {"error": str(e)}
