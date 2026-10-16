"""LINE Messaging API HTTP Client."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger("jarvis.extensions.line")

LINE_API_BASE = "https://api.line.me/v2/bot"


class LineClient:
    """Client for LINE Messaging API v2."""

    def __init__(self, channel_access_token: str) -> None:
        self.channel_access_token = channel_access_token

    def push_text(self, to: str, text: str) -> dict[str, Any]:
        """Push a text message to a user or group."""
        url = f"{LINE_API_BASE}/message/push"
        payload = {
            "to": to,
            "messages": [{"type": "text", "text": text}],
        }
        return self._post(url, payload)

    def reply_text(self, reply_token: str, text: str) -> dict[str, Any]:
        """Reply to an event with a text message."""
        url = f"{LINE_API_BASE}/message/reply"
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
        return self._post(url, payload)

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}",
        }
        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"ok": True}
        except Exception as e:
            logger.warning(f"LINE API request failed: {e}")
            return {"error": str(e)}
