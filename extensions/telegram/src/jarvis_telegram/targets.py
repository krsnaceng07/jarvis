from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TelegramTarget:
    """Represents a parsed Telegram target."""

    chat_id: str
    message_thread_id: int | None = None
    chat_type: Literal["direct", "group", "unknown"] = "unknown"

    @property
    def target_string(self) -> str:
        """Returns the canonical target string for JARVIS routing."""
        base = f"telegram:{self.chat_id}"
        if self.message_thread_id is not None:
            return f"{base}:topic:{self.message_thread_id}"
        return base


def parse_telegram_target(target_string: str) -> TelegramTarget:
    """Parse a JARVIS target string into a TelegramTarget.

    Expected formats:
      telegram:123456
      telegram:-100987654321
      telegram:-100987654321:topic:42
      123456  (fallback)
    """
    cleaned = target_string.strip()
    if cleaned.startswith("telegram:"):
        cleaned = cleaned[len("telegram:") :]

    topic_match = re.search(r":topic:(\d+)$", cleaned)
    if topic_match:
        thread_id = int(topic_match.group(1))
        chat_id = cleaned[: topic_match.start()]
    else:
        thread_id = None
        chat_id = cleaned

    # Telegram groups/supergroups typically start with '-'
    chat_type: Literal["direct", "group", "unknown"] = "unknown"
    if chat_id.startswith("-"):
        chat_type = "group"
    elif chat_id.isdigit():
        chat_type = "direct"

    return TelegramTarget(
        chat_id=chat_id,
        message_thread_id=thread_id,
        chat_type=chat_type,
    )
