"""Synology Chat outgoing webhook payload parsing and verification."""

from __future__ import annotations

import hmac
from typing import Any


def verify_synology_token(token_received: str, expected_token: str) -> bool:
    """Verify that token sent by Synology Chat matches the configured token."""
    if not token_received or not expected_token:
        return False
    return hmac.compare_digest(token_received, expected_token)


def parse_synology_webhook(form_data: dict[str, Any]) -> dict[str, Any]:
    """Parse outgoing webhook form fields from Synology Chat."""
    return {
        "token": form_data.get("token", ""),
        "channel_id": form_data.get("channel_id", ""),
        "channel_name": form_data.get("channel_name", ""),
        "channel_type": form_data.get("channel_type", ""),
        "user_id": form_data.get("user_id", ""),
        "username": form_data.get("username", ""),
        "post_id": form_data.get("post_id", ""),
        "timestamp": form_data.get("timestamp", ""),
        "text": form_data.get("text", ""),
        "raw": form_data,
    }
