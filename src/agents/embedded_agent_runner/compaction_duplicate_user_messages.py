"""jarvis.agents.embedded_agent_runner.compaction_duplicate_user_messages — dedupe user messages.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-duplicate-user-messages.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS` —
  the default 60s window.
- :data:`MIN_DUPLICATE_USER_MESSAGE_CHARS` —
  the minimum text length for a
  message to be considered a
  duplicate.
- :func:`dedupe_duplicate_user_messages_for_compaction` —
  drop later duplicate user
  messages while preserving the
  first prompt.
- :func:`collect_duplicate_user_message_entry_ids_for_compaction` —
  collect the session entry ids
  that should be skipped when
  building a compaction branch
  summary.

Phase 7.2a — focused minimal port.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


#: The default 60s window for
#: duplicate-user-message detection.
#: Mirrors
#: :data:`DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS`
#: (``compaction-duplicate-user-messages.ts:6``).
DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS: int = 60_000


#: The minimum text length for a
#: message to be considered a
#: duplicate. Mirrors
#: :data:`MIN_DUPLICATE_USER_MESSAGE_CHARS`
#: (``compaction-duplicate-user-messages.ts:7``).
MIN_DUPLICATE_USER_MESSAGE_CHARS: int = 24


def _normalize_user_message_content(
    content: Any,
) -> Optional[str]:
    """Normalize a user-message
    content block. Mirrors
    :func:`normalizeUserMessageContent`
    (``compaction-duplicate-user-messages.ts:26-46``).
    """
    if isinstance(content, str):
        return re.sub(r"\s+", " ", content).strip()
    if not isinstance(content, list):
        return None
    text_parts: list = []
    for block in content:
        if not isinstance(block, dict):
            return None
        if block.get("type") == "image":
            return None
        if block.get("type") == "text" and isinstance(
            block.get("text"), str
        ):
            text_parts.append(block["text"])
    return re.sub(r"\s+", " ", "\n".join(text_parts)).strip()


def _duplicate_signature(
    message: Any,
) -> Optional[dict]:
    """Build the duplicate-detection
    signature for a user message.
    Mirrors
    :func:`duplicateSignature`
    (``compaction-duplicate-user-messages.ts:48-65``).
    """
    if not isinstance(message, dict):
        return None
    if message.get("role") != "user":
        return None
    timestamp = message.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        return None
    text = _normalize_user_message_content(message.get("content"))
    if not text or len(text) < MIN_DUPLICATE_USER_MESSAGE_CHARS:
        return None
    metadata = message.get("__openclaw")
    sender_id = (
        metadata.get("senderId")
        if isinstance(metadata, dict)
        and isinstance(metadata.get("senderId"), str)
        else ""
    )
    normalized_text = text
    if hasattr(text, "normalize"):
        normalized_text = text.normalize("NFC").lower()  # type: ignore[attr-defined]
    else:
        normalized_text = text.lower()
    return {
        "key": json.dumps([sender_id, normalized_text]),
        "timestamp": float(timestamp),
    }


def dedupe_duplicate_user_messages_for_compaction(
    messages: list,
    options: Optional[dict] = None,
) -> list:
    """Drop later duplicate user
    messages while preserving the
    first prompt. Mirrors
    :func:`dedupeDuplicateUserMessagesForCompaction`
    (``compaction-duplicate-user-messages.ts:68-93`).
    """
    options = options or {}
    window_ms = int(
        options.get(
            "windowMs", DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS
        )
    )
    last_seen_at_by_key: dict = {}
    removed = 0
    result: list = []
    for message in messages:
        signature = _duplicate_signature(message)
        if not signature:
            result.append(message)
            continue
        last_seen_at = last_seen_at_by_key.get(signature["key"])
        last_seen_at_by_key[signature["key"]] = signature["timestamp"]
        if (
            isinstance(last_seen_at, (int, float))
            and signature["timestamp"] - last_seen_at <= window_ms
        ):
            removed += 1
            continue
        result.append(message)
    return result if removed > 0 else list(messages)


def collect_duplicate_user_message_entry_ids_for_compaction(
    entries: list,
    options: Optional[dict] = None,
) -> set:
    """Collect the session entry ids
    that should be skipped when
    building a compaction branch
    summary. Mirrors
    :func:`collectDuplicateUserMessageEntryIdsForCompaction`
    (``compaction-duplicate-user-messages.ts:96-119``).
    """
    options = options or {}
    window_ms = int(
        options.get(
            "windowMs", DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS
        )
    )
    last_seen_at_by_key: dict = {}
    duplicate_ids: set = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "message" or not isinstance(
            entry.get("id"), str
        ):
            continue
        message = entry.get("message")
        signature = _duplicate_signature(message)
        if not signature:
            continue
        last_seen_at = last_seen_at_by_key.get(signature["key"])
        last_seen_at_by_key[signature["key"]] = signature["timestamp"]
        if (
            isinstance(last_seen_at, (int, float))
            and signature["timestamp"] - last_seen_at <= window_ms
        ):
            duplicate_ids.add(entry["id"])
    return duplicate_ids


__all__ = [
    "DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS",
    "MIN_DUPLICATE_USER_MESSAGE_CHARS",
    "collect_duplicate_user_message_entry_ids_for_compaction",
    "dedupe_duplicate_user_messages_for_compaction",
]
