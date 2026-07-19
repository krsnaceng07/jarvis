"""TelegramChannel — send + listen for the Telegram channel."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

from .runtime import TelegramState  # noqa: TCH001

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger("jarvis.telegram")


class TelegramChannel:
    """Telegram channel surface (Phase 3 simplified port).

    Mirrors the parts of OpenClaw's ``extensions/telegram/src/channel.ts``
    that are needed for a single-user desktop assistant: ``send`` to
    a chat_id, ``listen`` via long-polling, and operator-pairing on
    the first inbound message.
    """

    def __init__(self, state: TelegramState) -> None:
        self.state = state

    def send(self, target: str, message: Any) -> dict[str, Any]:
        """Send a message to ``target`` (a chat_id string).

        Mirrors OpenClaw's ``ChannelPlugin.send``. Returns a dict with
        ``ok`` + ``message_id`` on success, ``ok=False`` + ``error`` on
        failure. ``message`` can be a string or a dict with
        ``{"text": ..., "reply_to": ...}``.
        """
        if not self.state.bot_token:
            return {"ok": False, "error": "no bot_token configured"}
        text = ""
        if isinstance(message, dict):
            text_value = cast("dict[str, object]", message).get("text", "")
            if text_value is not None:
                text = str(text_value)
        else:
            text = str(message)
        if not text:
            return {"ok": False, "error": "empty message"}
        # Late import — httpx is optional (the plugin works without
        # the bot_token being set; pairing fails gracefully).
        try:
            import httpx
        except ImportError:
            return {"ok": False, "error": "httpx not installed"}
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{self.state.bot_token}/sendMessage",
                json={"chat_id": target, "text": text},
                timeout=10.0,
            )
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "message_id": data["result"]["message_id"]}
            return {"ok": False, "error": str(data.get("description", "unknown"))}
        except Exception as e:
            _log.warning("telegram.send failed: %s", e)
            return {"ok": False, "error": str(e)}

    def listen(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Long-poll Telegram's getUpdates. On each message, call
        ``callback({chat_id, text, message_id, from_id})``.

        On the FIRST inbound message, the bot pairs: it remembers
        ``chat_id`` in ``~/.jarvis/telegram.json`` (operator-only
        pairing — mirrors OpenClaw's account-resolution flow).
        """
        if not self.state.bot_token:
            _log.warning("telegram.listen: no bot_token; not starting")
            return
        try:
            import httpx
        except ImportError:
            _log.warning("telegram.listen: httpx not installed")
            return

        offset = 0
        interval = self.state.polling_interval_sec
        _log.info("telegram.listen: starting (interval=%ds)", interval)
        while not self.state.stop_flag:
            try:
                r = httpx.get(
                    f"https://api.telegram.org/bot{self.state.bot_token}/getUpdates",
                    params={"timeout": 25, "offset": offset + 1},
                    timeout=30.0,
                )
                data = r.json()
            except Exception as e:
                _log.warning("telegram.getUpdates failed: %s", e)
                time.sleep(interval * 5)
                continue
            for upd in data.get("result", []):
                offset = max(offset, upd["update_id"])
                msg = upd.get("message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                from_id = str(msg.get("from", {}).get("id", ""))
                # Pair on first message (operator-only).
                if not self.state.paired_chat_id:
                    self.state.set_paired_chat_id(chat_id)
                    _log.info("telegram: paired with chat_id=%s", chat_id)
                # Dispatch to the host's slash-command router (if
                # the text starts with /). For now we just call the
                # callback; the host wires routing in Phase 3 wiring.
                callback(
                    {
                        "chat_id": chat_id,
                        "text": text,
                        "from_id": from_id,
                        "message_id": msg.get("message_id"),
                    }
                )
            time.sleep(interval)


__all__ = ["TelegramChannel"]
