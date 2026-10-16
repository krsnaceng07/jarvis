"""Formatting and message construction for Mattermost posts."""

from __future__ import annotations

from typing import Any


def format_mattermost_post(
    message: str,
    channel_id: str,
    root_id: str | None = None,
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a Mattermost post object for /api/v4/posts."""
    payload: dict[str, Any] = {
        "channel_id": channel_id,
        "message": message,
    }
    if root_id:
        payload["root_id"] = root_id
    if props:
        payload["props"] = props
    return payload


def build_interactive_attachment(
    title: str,
    text: str,
    color: str = "#2389D7",
    actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Construct an interactive slack-compatible attachment for Mattermost."""
    att: dict[str, Any] = {
        "title": title,
        "text": text,
        "color": color,
    }
    if actions:
        built_actions = []
        for a in actions:
            built_actions.append(
                {
                    "id": a.get("id", "btn"),
                    "name": a.get("name", "Action"),
                    "integration": {
                        "url": a.get("url", ""),
                        "context": {"action": a.get("action", "")},
                    },
                }
            )
        att["actions"] = built_actions
    return att
