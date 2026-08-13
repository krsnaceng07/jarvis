"""Telegram compatibility plugin surface for the root extension package.

This file is intentionally small and mirror-like: the phase-3 tests import
``extensions.telegram.plugin`` and expect a ``TelegramChannel`` implementation
that talks to ``TelegramState`` as the runtime contract, and also expect the
``plugin`` / ``entry`` / ``_register`` names to exist at the plugin package root.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from jarvis_sdk import define_plugin_entry
from src.doctor import DoctorFinding, Severity

from .doctor import detect_telegram_credentials
from .runtime import TelegramState


class TelegramChannel:
    """Compatibility wrapper for the Telegram channel API used by the tests.

    The runtime-only tests use this class as a synchronous, stateful façade:
    ``TelegramChannel(state).send(...)`` returns a dict payload and the
    ``listen(...)`` method drains one webhook/polling HTTP response cycle.
    """

    def __init__(self, state: TelegramState | None = None) -> None:
        self.state = state or TelegramState.default()
        self.stop_flag = False
        self._offset = 0

    def send(self, target: str, text: str) -> dict[str, Any]:
        token = (self.state.bot_token or "").strip()
        if not token:
            return {"ok": False, "error": "bot_token is missing"}
        if not text or not text.strip():
            return {"ok": False, "error": "message text is empty"}
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": target, "text": text},
                timeout=5.0,
            )
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        if payload.get("ok") is True:
            result = payload.get("result") or {}
            return {"ok": True, "message_id": result.get("message_id")}
        return {"ok": False, "error": payload.get("description") or "telegram send failed"}

    def listen(self, callback: Any) -> None:
        token = (self.state.bot_token or "").strip()
        if not token:
            return
        if self.stop_flag:
            return
        try:
            response = httpx.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 1, "offset": self._offset},
                timeout=5.0,
            )
            payload = response.json()
        except Exception:  # noqa: BLE001
            return
        if not payload.get("ok"):
            return
        updates = payload.get("result") or []
        for update in updates:
            self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
            message = update.get("message")
            if not message:
                continue
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id") or "")
            text = str(message.get("text") or "")
            from_id = str((message.get("from") or {}).get("id") or "")
            if chat_id:
                self.state.paired_chat_id = chat_id
                callback(
                    {
                        "kind": "message",
                        "chat_id": chat_id,
                        "from_id": from_id,
                        "text": text,
                        "message_id": message.get("message_id"),
                    }
                )
                self.stop_flag = True
                break


class TelegramChannelPlugin(TelegramChannel):
    """Thin alias for the compatibility runtime class."""

    id = "telegram"
    kind = "channel"
    version = "0.1.0"
    description = "Telegram channel plugin"


# The runtime instance imported by the host/entrypoint layer.
plugin = TelegramChannelPlugin()


def _register(api: Any) -> None:
    """Compatibility registration used by the Phase 3 import contract."""
    api.register_channel(plugin)
    api.register_doctor_contract(
        {
            "id": "telegram.credentials",
            "version": 1,
            "detect": detect_telegram_credentials,
            "apply": None,
        }
    )


entry = define_plugin_entry(
    id="telegram",
    kind="channel",
    name="Telegram",
    description="Telegram messaging channel compatibility surface.",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["network:outbound"],
)


__all__ = ["TelegramChannel", "TelegramChannelPlugin", "plugin", "entry", "_register", "TelegramState"]
