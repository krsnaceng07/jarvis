"""Unit tests for Google Chat extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.googlechat.src.format import markdown_to_google_chat, build_google_chat_card
from extensions.googlechat.src.webhook import parse_google_chat_event
from extensions.googlechat.src.client import GoogleChatClient
from extensions.googlechat.plugin import googlechat_plugin


def test_markdown_to_google_chat() -> None:
    md = "Here is **bold** text and ~~strike~~ with [Link](https://example.com) and `code`."
    formatted = markdown_to_google_chat(md)
    assert "*bold*" in formatted
    assert "~strike~" in formatted
    assert "<https://example.com|Link>" in formatted
    assert "`code`" in formatted


def test_build_google_chat_card() -> None:
    card = build_google_chat_card(
        title="Alert",
        subtitle="System Status",
        text="Everything is **healthy**.",
        buttons=[{"text": "Dashboard", "url": "https://dashboard.example.com"}],
    )
    assert "cardsV2" in card
    v2 = card["cardsV2"][0]["card"]
    assert v2["header"]["title"] == "Alert"
    assert v2["header"]["subtitle"] == "System Status"
    widgets = v2["sections"][0]["widgets"]
    assert len(widgets) == 2
    assert "*healthy*" in widgets[0]["textParagraph"]["text"]
    assert widgets[1]["buttonList"]["buttons"][0]["text"] == "Dashboard"


def test_parse_google_chat_event() -> None:
    event = {
        "type": "MESSAGE",
        "space": {"name": "spaces/AAA", "type": "ROOM"},
        "message": {
            "text": "Hello bot",
            "sender": {"displayName": "Alice"},
            "thread": {"name": "spaces/AAA/threads/123"},
        },
    }
    parsed = parse_google_chat_event(event)
    assert parsed["event_type"] == "MESSAGE"
    assert parsed["space_name"] == "spaces/AAA"
    assert parsed["sender"] == "Alice"
    assert parsed["text"] == "Hello bot"
    assert parsed["thread_name"] == "spaces/AAA/threads/123"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(
        GoogleChatClient, "send_text", return_value={"name": "spaces/AAA/messages/1"}
    ):
        res = await googlechat_plugin.send(
            "https://chat.googleapis.com/v1/spaces/AAA/messages", "Test message"
        )
        assert res.is_ok
        assert res.unwrap()["name"] == "spaces/AAA/messages/1"
