"""Zalo Official Account OpenAPI Client."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger("jarvis.extensions.zalo")

ZALO_OA_MESSAGE_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"


class ZaloClient:
    """Client for Zalo OA messages."""

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def send_text(self, user_id: str, text: str) -> dict[str, Any]:
        """Send a consultation customer support text message to a user."""
        payload = {
            "recipient": {"user_id": user_id},
            "message": {"text": text},
        }
        return self._post(ZALO_OA_MESSAGE_URL, payload)

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "access_token": self.access_token,
        }
        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"error": 0, "message": "Success"}
        except Exception as e:
            logger.warning(f"Zalo API request failed: {e}")
            return {"error": -1, "message": str(e)}
