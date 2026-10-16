"""Nextcloud Talk (Spreed) REST API Client."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger("jarvis.extensions.nextcloud_talk")


class NextcloudTalkClient:
    """Client for Nextcloud Talk OCS API."""

    def __init__(
        self,
        server_url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.username = username
        self.password = password

    def send_chat_message(
        self,
        room_token: str,
        message: str,
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        """Send message to a Nextcloud Talk room."""
        url = f"{self.server_url}/ocs/v2.php/apps/spreed/api/v1/chat/{room_token}"
        payload: dict[str, Any] = {"message": message}
        if reply_to is not None:
            payload["replyTo"] = reply_to

        return self._post(url, payload)

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "OCS-APIRequest": "true",
            "Accept": "application/json",
        }
        if self.username and self.password:
            creds = f"{self.username}:{self.password}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(creds).decode('utf-8')}"

        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"ok": True}
        except Exception as e:
            logger.warning(f"Nextcloud Talk API request failed: {e}")
            return {"error": str(e)}
