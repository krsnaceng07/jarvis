"""Mattermost REST API v4 Client."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from .format import format_mattermost_post

logger = logging.getLogger("jarvis.extensions.mattermost")


class MattermostClient:
    """Mattermost v4 API Client."""

    def __init__(
        self, server_url: str = "http://localhost:8065", bot_token: str | None = None
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.bot_token = bot_token

    def create_post(
        self,
        channel_id: str,
        message: str,
        root_id: str | None = None,
        props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new post in a channel or thread."""
        url = f"{self.server_url}/api/v4/posts"
        payload = format_mattermost_post(
            message=message, channel_id=channel_id, root_id=root_id, props=props
        )
        return self._post(url, payload)

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {self.bot_token}"} if self.bot_token else {}),
        }
        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"ok": True}
        except Exception as e:
            logger.warning(f"Mattermost API call failed: {e}")
            return {"error": str(e)}
