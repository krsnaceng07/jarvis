"""Google Chat REST API client for sending messages and cards to spaces."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from .format import markdown_to_google_chat, build_google_chat_card

logger = logging.getLogger("jarvis.extensions.googlechat")


class GoogleChatClient:
    """HTTP Client for Google Chat Webhooks and REST API."""

    def __init__(self, webhook_url: str | None = None, token_provider: Any = None) -> None:
        self.webhook_url = webhook_url
        self.token_provider = token_provider

    def send_text(
        self, space_or_url: str, text: str, thread_key: str | None = None
    ) -> dict[str, Any]:
        """Send formatted text message to a space webhook or URL."""
        url = space_or_url if space_or_url.startswith("http") else (self.webhook_url or "")
        if not url:
            return {"error": "no_destination_url"}

        payload: dict[str, Any] = {"text": markdown_to_google_chat(text)}
        if thread_key:
            payload["thread"] = {"threadKey": thread_key}

        return self._post(url, payload)

    def send_card(
        self,
        space_or_url: str,
        title: str,
        text: str,
        subtitle: str | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Send card v2 message."""
        url = space_or_url if space_or_url.startswith("http") else (self.webhook_url or "")
        if not url:
            return {"error": "no_destination_url"}

        payload = build_google_chat_card(title=title, subtitle=subtitle, text=text, buttons=buttons)
        return self._post(url, payload)

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json; charset=UTF-8"})
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"ok": True}
        except Exception as e:
            logger.warning(f"Google Chat request failed: {e}")
            return {"error": str(e)}
