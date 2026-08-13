"""Channel reply formatting — prefix, sender label, truncation.

Mirrors OpenClaw's ``src/channels/reply-prefix.ts`` +
``src/channels/sender-label.ts``.

Channel plugins use these helpers to format agent replies before
sending. The key concerns are:
  - Stripping or preserving markdown (channels differ in support)
  - Adding a reply-prefix (e.g. "JARVIS: ") for multi-user channels
  - Truncating at channel limits (Telegram: 4096, Discord: 2000)
  - Splitting long messages into multiple sends
"""

from __future__ import annotations

import re


# ── Channel message length limits ──────────────────────────────────────

LIMITS: dict[str, int] = {
    "telegram": 4096,
    "discord": 2000,
    "slack": 3000,
    "whatsapp": 1024,
    "default": 4000,
}


def channel_limit(channel_id: str) -> int:
    """Return the character limit for ``channel_id``."""
    return LIMITS.get(channel_id, LIMITS["default"])


# ── Reply prefix ───────────────────────────────────────────────────────


def format_reply(
    text: str,
    *,
    channel_id: str = "default",
    prefix: str = "",
    max_chars: int | None = None,
) -> str:
    """Format an agent reply for a channel.

    Applies the prefix and truncates at the channel's character limit.
    Does NOT split — use ``split_reply()`` for multi-message sends.

    Parameters
    ----------
    text : str
        The agent's raw reply text.
    channel_id : str
        Used to look up the default character limit.
    prefix : str
        Optional prefix prepended to every reply (e.g. ``"🤖 "``).
    max_chars : int | None
        Override the channel's default limit.
    """
    limit = max_chars if max_chars is not None else channel_limit(channel_id)
    body = (prefix + text) if prefix else text
    if len(body) <= limit:
        return body
    # Truncate with ellipsis.
    return body[: limit - 1] + "…"


def split_reply(
    text: str,
    *,
    channel_id: str = "default",
    prefix: str = "",
    max_chars: int | None = None,
) -> list[str]:
    """Split a long reply into chunks that fit within the channel limit.

    Mirrors OpenClaw's ``splitReply`` helper. Tries to split on
    paragraph / sentence boundaries before hard-splitting at character
    limit.

    Returns a list of 1+ strings, each within the limit.
    """
    limit = max_chars if max_chars is not None else channel_limit(channel_id)
    if prefix:
        # Prefix only on the first chunk.
        first_limit = limit - len(prefix)
        parts = _split_text(text, first_limit, limit)
        if parts:
            parts[0] = prefix + parts[0]
        return parts
    return _split_text(text, limit, limit)


def _split_text(text: str, first_limit: int, rest_limit: int) -> list[str]:
    """Split ``text`` on paragraph/newline boundaries first."""
    if len(text) <= first_limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    limit = first_limit

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try to split at a paragraph break within the limit.
        slice_ = remaining[:limit]
        last_para = slice_.rfind("\n\n")
        last_newline = slice_.rfind("\n")
        last_space = slice_.rfind(" ")

        if last_para > limit // 2:
            cut = last_para + 2
        elif last_newline > limit // 2:
            cut = last_newline + 1
        elif last_space > limit // 2:
            cut = last_space + 1
        else:
            cut = limit  # hard cut

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
        limit = rest_limit

    return [c for c in chunks if c]


# ── Sender label ───────────────────────────────────────────────────────


def sender_label(
    sender_id: str,
    display_name: str | None = None,
    *,
    is_owner: bool = False,
    bot_name: str = "JARVIS",
) -> str:
    """Format a sender label for multi-user channel messages.

    Mirrors OpenClaw's ``senderLabel`` helper from
    ``src/channels/sender-label.ts``.

    Parameters
    ----------
    sender_id : str
        Channel-native user id.
    display_name : str | None
        Human-readable name (first name, username, etc.).
    is_owner : bool
        True when the sender is the operator.
    bot_name : str
        The bot's display name (used in bot-originated messages).
    """
    if display_name:
        name = display_name.strip()
    else:
        name = sender_id

    if is_owner:
        return f"[Owner/{name}]"
    return f"[{name}]"


# ── Markdown strip ─────────────────────────────────────────────────────

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_BOLD_ITALIC = re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}")
_CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Strip common markdown formatting from ``text``.

    Used by channels that don't support markdown (e.g. plain SMS).
    Preserves code content but removes backticks and fence markers.
    """
    text = _CODE_BLOCK.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _BOLD_ITALIC.sub(r"\1", text)
    text = _HEADING.sub("", text)
    return text.strip()


__all__ = [
    "LIMITS",
    "channel_limit",
    "format_reply",
    "split_reply",
    "sender_label",
    "strip_markdown",
]
