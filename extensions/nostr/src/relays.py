"""Nostr relay message formatting and client support."""

from __future__ import annotations

import json
from typing import Any

from .events import NostrEvent


def format_publish_event_message(event: NostrEvent) -> str:
    """Format ['EVENT', event_dict] message for Nostr relay websocket."""
    return json.dumps(["EVENT", event.to_dict()], separators=(",", ":"), ensure_ascii=False)


def format_subscription_request(subscription_id: str, filters: list[dict[str, Any]]) -> str:
    """Format ['REQ', sub_id, filter1, filter2...] message for Nostr relay."""
    payload = ["REQ", subscription_id]
    payload.extend(filters)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
