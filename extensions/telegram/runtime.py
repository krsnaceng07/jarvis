"""Telegram runtime compatibility surface.

This package-level module is the minimal public runtime shape the
Phase 3 tests import via ``from extensions.telegram import runtime`` and
``from extensions.telegram.runtime import TelegramState``.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class TelegramState:
    """Small persisted config/state holder for Telegram.

    The tests only rely on a handful of fields and persistence semantics:
    ``bot_token`` (string), ``paired_chat_id`` (string), and
    ``polling_interval_sec`` (integer clamped to at least 1).
    """

    _default: TelegramState | None = None
    _lock = threading.Lock()

    def __init__(self, state_path: Path | None = None) -> None:
        self.bot_token = ""
        self.paired_chat_id = ""
        self.polling_interval_sec = 1
        self._state_path = state_path
        self._load()

    @classmethod
    def default(cls) -> "TelegramState":
        with cls._lock:
            if cls._default is None:
                data_dir = Path(os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis"))
                cls._default = cls(data_dir / "core" / "telegram.json")
            return cls._default

    def set_bot_token(self, token: str) -> None:
        self.bot_token = token or ""
        self._save()

    def set_paired_chat_id(self, chat_id: str) -> None:
        self.paired_chat_id = chat_id or ""
        self._save()

    def set_polling_interval(self, value: int) -> None:
        if value < 1:
            value = 1
        self.polling_interval_sec = value
        self._save()

    def _save(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "bot_token": self.bot_token,
            "paired_chat_id": self.paired_chat_id,
            "polling_interval_sec": self.polling_interval_sec,
        }
        self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if self._state_path is None:
            return
        if not self._state_path.exists():
            env_token = os.environ.get("JARVIS_TELEGRAM_BOT_TOKEN")
            if env_token:
                self.bot_token = env_token
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self.bot_token = str(data.get("bot_token") or os.environ.get("JARVIS_TELEGRAM_BOT_TOKEN") or "")
            self.paired_chat_id = str(data.get("paired_chat_id") or "")
            self.polling_interval_sec = int(data.get("polling_interval_sec") or 1)
            if self.polling_interval_sec < 1:
                self.polling_interval_sec = 1


__all__ = ["TelegramState"]
