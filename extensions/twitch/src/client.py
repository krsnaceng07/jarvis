"""Twitch Chat and Helix API client."""

from __future__ import annotations

import logging
from typing import Any

from .tags import parse_twitch_tags, extract_twitch_user_info

logger = logging.getLogger("jarvis.extensions.twitch")


class TwitchChatClient:
    """Twitch Chat client helper."""

    def __init__(
        self,
        oauth_token: str,
        bot_username: str = "jarvis_bot",
        channels: list[str] | None = None,
    ) -> None:
        self.oauth_token = (
            oauth_token if oauth_token.startswith("oauth:") else f"oauth:{oauth_token}"
        )
        self.bot_username = bot_username.lower()
        self.channels = [c.lower().lstrip("#") for c in (channels or [])]

    def format_chat_message(self, channel: str, message: str) -> str:
        """Format PRIVMSG line for Twitch IRC socket."""
        clean_channel = channel.lower().lstrip("#")
        return f"PRIVMSG #{clean_channel} :{message}\r\n"

    def parse_incoming_privmsg(self, raw_line: str) -> dict[str, Any] | None:
        """Parse raw Twitch PRIVMSG line with tags."""
        if not raw_line or "PRIVMSG" not in raw_line:
            return None

        tags_dict: dict[str, str] = {}
        line = raw_line.strip("\r\n")
        if line.startswith("@"):
            tag_part, rest = line.split(" ", 1)
            tags_dict = parse_twitch_tags(tag_part)
            line = rest

        # Format: :username!username@username.tmi.twitch.tv PRIVMSG #channel :message
        parts = line.split(" ", 3)
        if len(parts) >= 4 and parts[1] == "PRIVMSG":
            channel = parts[2].lstrip("#")
            text = parts[3].lstrip(":")
            user_info = extract_twitch_user_info(tags_dict)
            return {
                "channel": channel,
                "text": text,
                "user": user_info,
                "tags": tags_dict,
            }

        return None
