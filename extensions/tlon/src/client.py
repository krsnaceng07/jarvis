"""Urbit Eyre HTTP API Client."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from .format import format_urbit_chat_post

logger = logging.getLogger("jarvis.extensions.tlon")


class UrbitClient:
    """Urbit ship HTTP client for poke and scry."""

    def __init__(self, ship_url: str, ship_name: str, code: str) -> None:
        self.ship_url = ship_url.rstrip("/")
        self.ship_name = ship_name if ship_name.startswith("~") else f"~{ship_name}"
        self.code = code
        self._cookie: str | None = None

    def login(self) -> bool:
        """Authenticate with Urbit ship Eyre server to acquire session cookie."""
        url = f"{self.ship_url}/~/login"
        payload = json.dumps({"password": self.code}).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                headers = resp.headers
                cookie = headers.get("Set-Cookie")
                if cookie:
                    self._cookie = cookie.split(";")[0]
                    return True
                return True
        except Exception as e:
            logger.warning(f"Urbit login failed: {e}")
            return False

    def post_chat(self, channel_nest: str, text: str) -> dict[str, Any]:
        """Poke chat app with a new message."""
        url = f"{self.ship_url}/~/poke"
        chat_post = format_urbit_chat_post(author=self.ship_name, text=text)
        poke_data = {
            "app": "chat",
            "mark": "chat-action",
            "json": {
                "post": {
                    "add": {
                        "whom": channel_nest,
                        "post": chat_post["post"],
                    }
                }
            },
        }
        return self._post_json(url, poke_data)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            **({"Cookie": self._cookie} if self._cookie else {}),
        }
        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"ok": True}
        except Exception as e:
            logger.warning(f"Urbit request failed: {e}")
            return {"error": str(e)}
