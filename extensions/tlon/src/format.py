"""Tlon / Urbit message formatting utilities."""

from __future__ import annotations

from typing import Any


def format_urbit_chat_post(author: str, text: str) -> dict[str, Any]:
    """Format an Urbit chat action post payload."""
    return {
        "post": {
            "author": author,
            "contents": [{"inline": [text]}],
            "sent": 0,
        }
    }
