from __future__ import annotations

import logging
from typing import Any

import httpx

_log = logging.getLogger("jarvis.telegram.client")


class TelegramClient:
    """Async wrapper for the Telegram Bot API."""

    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_updates(self, offset: int = 0, timeout: int = 25) -> list[dict[str, Any]]:
        """Long poll for updates."""
        try:
            r = await self.client.get(
                f"{self.base_url}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": timeout,
                    "allowed_updates": ["message", "callback_query"],
                },
            )
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return data.get("result", [])
            _log.error("Telegram getUpdates error: %s", data.get("description"))
        except Exception as e:
            _log.warning("Telegram getUpdates request failed: %s", e)
        return []

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict | None = None,
    ) -> dict[str, Any]:
        """Send a message to a chat."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            r = await self.client.post(f"{self.base_url}/sendMessage", json=payload)
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "message_id": data["result"]["message_id"]}
            error_desc = data.get("description", "Unknown Error")
            _log.error("Telegram sendMessage error: %s", error_desc)
            return {"ok": False, "error": error_desc}
        except Exception as e:
            _log.warning("Telegram sendMessage request failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def send_location(
        self,
        chat_id: str,
        latitude: float,
        longitude: float,
        horizontal_accuracy: float | None = None,
        live_period: int | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict | None = None,
    ) -> dict[str, Any]:
        """Send a location to a chat."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
        }
        if horizontal_accuracy:
            payload["horizontal_accuracy"] = horizontal_accuracy
        if live_period:
            payload["live_period"] = live_period
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            r = await self.client.post(f"{self.base_url}/sendLocation", json=payload)
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "message_id": data["result"]["message_id"]}
            error_desc = data.get("description", "Unknown Error")
            _log.error("Telegram sendLocation error: %s", error_desc)
            return {"ok": False, "error": error_desc}
        except Exception as e:
            _log.warning("Telegram sendLocation request failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def send_venue(
        self,
        chat_id: str,
        latitude: float,
        longitude: float,
        title: str,
        address: str,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict | None = None,
    ) -> dict[str, Any]:
        """Send a venue to a chat."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
            "title": title,
            "address": address,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            r = await self.client.post(f"{self.base_url}/sendVenue", json=payload)
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "message_id": data["result"]["message_id"]}
            error_desc = data.get("description", "Unknown Error")
            _log.error("Telegram sendVenue error: %s", error_desc)
            return {"ok": False, "error": error_desc}
        except Exception as e:
            _log.warning("Telegram sendVenue request failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> bool:
        """Acknowledge a callback query."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert

        try:
            r = await self.client.post(f"{self.base_url}/answerCallbackQuery", json=payload)
            r.raise_for_status()
            return r.json().get("ok", False)
        except Exception as e:
            _log.warning("Telegram answerCallbackQuery failed: %s", e)
            return False

    async def get_me(self) -> dict[str, Any]:
        """Test the bot token and retrieve bot identity from /getMe."""
        try:
            r = await self.client.get(f"{self.base_url}/getMe")
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "result": data.get("result", {})}
            error_desc = data.get("description", "Unknown Error")
            _log.error("Telegram getMe error: %s", error_desc)
            return {"ok": False, "error": error_desc}
        except Exception as e:
            _log.warning("Telegram getMe request failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def send_voice(
        self,
        chat_id: str,
        voice_bytes: bytes,
        filename: str = "voice.wav",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, Any]:
        """Send an interactive playable voice message to a chat."""
        data: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            data["message_thread_id"] = message_thread_id

        mime = "audio/ogg" if filename.endswith(".ogg") else "audio/wav"
        files = {"voice": (filename, voice_bytes, mime)}

        try:
            r = await self.client.post(
                f"{self.base_url}/sendVoice",
                data=data,
                files=files,
            )
            r.raise_for_status()
            res_data = r.json()
            if res_data.get("ok"):
                return {"ok": True, "result": res_data.get("result", {})}
            error_desc = res_data.get("description", "Unknown Error")
            _log.error("Telegram sendVoice error: %s; falling back to sendAudio", error_desc)
            return await self.send_audio(
                chat_id=chat_id,
                audio_bytes=voice_bytes,
                filename="voice.wav",
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                message_thread_id=message_thread_id,
            )
        except Exception as e:
            _log.warning("Telegram sendVoice request failed, trying sendAudio: %s", e)
            return await self.send_audio(
                chat_id=chat_id,
                audio_bytes=voice_bytes,
                filename="voice.wav",
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                message_thread_id=message_thread_id,
            )

    async def send_audio(
        self,
        chat_id: str,
        audio_bytes: bytes,
        filename: str = "voice.wav",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, Any]:
        """Send an audio file to a chat."""
        data: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            data["message_thread_id"] = message_thread_id

        files = {"audio": (filename, audio_bytes, "audio/wav")}

        try:
            r = await self.client.post(
                f"{self.base_url}/sendAudio",
                data=data,
                files=files,
            )
            r.raise_for_status()
            res_data = r.json()
            if res_data.get("ok"):
                return {"ok": True, "result": res_data.get("result", {})}
            error_desc = res_data.get("description", "Unknown Error")
            _log.error("Telegram sendAudio error: %s", error_desc)
            return {"ok": False, "error": error_desc}
        except Exception as e:
            _log.warning("Telegram sendAudio request failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()
