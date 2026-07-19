"""TelegramState — persistent configuration for the Telegram channel.

Phase 3. Holds:
  - ``bot_token`` — from the user config or env var
  - ``paired_chat_id`` — the operator's chat_id (set on first inbound
    message; mirrors OpenClaw's account-resolution flow)
  - ``polling_interval_sec`` — how often to long-poll
  - ``stop_flag`` — for clean shutdown

The state persists to ``~/.jarvis/telegram.json`` (cross-session
operator identity).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class TelegramState:
    """Persistent Telegram channel state.

    Mirrors OpenClaw's per-account state (``extensions/telegram/src/accounts.js``).
    Single-instance-per-process; the default() accessor returns the
    process-wide instance rooted at ``$JARVIS_DATA_DIR/telegram.json``
    (or ``~/.jarvis/telegram.json``).
    """

    _default: TelegramState | None = None
    _lock = threading.Lock()

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path
        self.bot_token: str = ""
        self.paired_chat_id: str = ""
        self.polling_interval_sec: int = 1
        self.stop_flag: bool = False
        self._mu = threading.Lock()
        if store_path and store_path.exists():
            self._load()
        # Allow env-var override of bot_token (e.g. for CI tests).
        if not self.bot_token:
            env_token = os.environ.get("JARVIS_TELEGRAM_BOT_TOKEN")
            if env_token:
                self.bot_token = env_token

    @classmethod
    def default(cls) -> TelegramState:
        with cls._lock:
            if cls._default is None:
                data_dir = Path(os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis"))
                cls._default = cls(data_dir / "telegram.json")
            return cls._default

    def set_bot_token(self, token: str) -> None:
        with self._mu:
            self.bot_token = token
        self._save()

    def set_paired_chat_id(self, chat_id: str) -> None:
        with self._mu:
            self.paired_chat_id = chat_id
        self._save()

    def set_polling_interval(self, seconds: int) -> None:
        with self._mu:
            self.polling_interval_sec = max(1, int(seconds))
        self._save()

    def to_dict(self) -> dict[str, Any]:
        with self._mu:
            return {
                "bot_token": self.bot_token,
                "paired_chat_id": self.paired_chat_id,
                "polling_interval_sec": self.polling_interval_sec,
            }

    # ── Persistence ────────────────────────────────────────────────

    def _save(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if self._store_path is None:
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.bot_token = str(data.get("bot_token", ""))
        self.paired_chat_id = str(data.get("paired_chat_id", ""))
        self.polling_interval_sec = int(data.get("polling_interval_sec", 1))


__all__ = ["TelegramState"]
