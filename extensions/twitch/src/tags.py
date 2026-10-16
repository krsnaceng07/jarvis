"""Twitch IRC message tags parser."""

from __future__ import annotations

from typing import Any


def parse_twitch_tags(tag_str: str) -> dict[str, str]:
    """Parse IRC v3 tags string from Twitch (e.g. '@badge-info=;badges=broadcaster/1;color=#FF0000')."""
    if tag_str.startswith("@"):
        tag_str = tag_str[1:]

    tags: dict[str, str] = {}
    for part in tag_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            # Unescape Twitch tag characters (\: -> ;, \s -> space, \\ -> \)
            clean_v = v.replace(r"\:", ";").replace(r"\s", " ").replace(r"\\", "\\")
            tags[k] = clean_v
        elif part:
            tags[part] = ""
    return tags


def extract_twitch_user_info(tags: dict[str, str]) -> dict[str, Any]:
    """Extract structured user information from Twitch IRC tags."""
    return {
        "display_name": tags.get("display-name", ""),
        "user_id": tags.get("user-id", ""),
        "color": tags.get("color", ""),
        "mod": tags.get("mod") == "1",
        "subscriber": tags.get("subscriber") == "1",
        "badges": tags.get("badges", "").split(",") if tags.get("badges") else [],
    }
