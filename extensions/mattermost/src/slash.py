"""Mattermost slash command and outgoing webhook payload parsing."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.extensions.mattermost")


def parse_slash_command(form_data: dict[str, Any]) -> dict[str, Any]:
    """Parse Mattermost slash command form payload."""
    return {
        "channel_id": form_data.get("channel_id", ""),
        "channel_name": form_data.get("channel_name", ""),
        "command": form_data.get("command", ""),
        "text": form_data.get("text", ""),
        "user_id": form_data.get("user_id", ""),
        "user_name": form_data.get("user_name", ""),
        "team_id": form_data.get("team_id", ""),
        "team_domain": form_data.get("team_domain", ""),
        "token": form_data.get("token", ""),
        "trigger_id": form_data.get("trigger_id", ""),
    }


def format_slash_response(
    text: str,
    response_type: str = "ephemeral",
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Format slash command response JSON."""
    payload: dict[str, Any] = {
        "response_type": response_type,
        "text": text,
    }
    if attachments:
        payload["attachments"] = attachments
    return payload
