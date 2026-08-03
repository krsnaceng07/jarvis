"""jarvis.shared.chat_envelope — channel-prefix envelope helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/chat-envelope.ts``.
"""
from __future__ import annotations

import re

#: Recognized channel labels that may prefix chat text.
_ENVELOPE_CHANNELS = [
    "WebChat",
    "WhatsApp",
    "Telegram",
    "Signal",
    "Slack",
    "Discord",
    "Google Chat",
    "iMessage",
    "Teams",
    "Matrix",
    "Zalo",
    "Zalo Personal",
]

_ENVELOPE_PREFIX_RE = re.compile(r"^\[([^\]]+)\]\s*")
_MESSAGE_ID_LINE_RE = re.compile(r"^\s*\[message_id:\s*[^\]]+\]\s*$", re.IGNORECASE)
_ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z\b")
_DATETIME_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}\b")


def _looks_like_envelope_header(header: str) -> bool:
    if _ISO_TS_RE.search(header):
        return True
    if _DATETIME_TS_RE.search(header):
        return True
    return any(header.startswith(f"{label} ") for label in _ENVELOPE_CHANNELS)


def strip_envelope(text: str) -> str:
    """Remove recognized channel/timestamp prefixes from ``text``.

    Mirrors :func:`stripEnvelope` (``shared/chat-envelope.ts``).
    """
    match = _ENVELOPE_PREFIX_RE.match(text)
    if not match:
        return text
    header = match.group(1) or ""
    # Only strip known generated envelopes; arbitrary [name] text may be part
    # of the user-authored message.
    if not _looks_like_envelope_header(header):
        return text
    return text[len(match.group(0)):]


def strip_message_id_hints(text: str) -> str:
    """Remove standalone ``[message_id: ...]`` hint lines.

    Mirrors :func:`stripMessageIdHints` (``shared/chat-envelope.ts``).
    """
    if "[message_id:" not in text.lower():
        return text
    lines = text.splitlines()
    filtered = [line for line in lines if not _MESSAGE_ID_LINE_RE.match(line)]
    return text if len(filtered) == len(lines) else "\n".join(filtered)


__all__ = ["strip_envelope", "strip_message_id_hints"]
