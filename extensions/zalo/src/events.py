"""Zalo Webhook event parsing and models."""

from __future__ import annotations

from typing import Any


def parse_zalo_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse Zalo OA webhook payload."""
    event_name = payload.get("event_name", "unknown")
    app_id = payload.get("app_id", "")
    oa_id = payload.get("oa_id", "")
    sender = payload.get("sender", {})
    sender_id = sender.get("id", "")
    recipient = payload.get("recipient", {})
    recipient_id = recipient.get("id", "")

    message = payload.get("message", {})
    text = message.get("text", "")
    msg_id = message.get("msg_id", "")

    return {
        "event_name": event_name,
        "app_id": app_id,
        "oa_id": oa_id,
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "text": text,
        "msg_id": msg_id,
        "raw": payload,
    }
