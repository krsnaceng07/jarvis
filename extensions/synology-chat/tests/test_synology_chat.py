"""Unit tests for Synology Chat extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.synology_chat.src.webhook import verify_synology_token, parse_synology_webhook
from extensions.synology_chat.src.client import SynologyChatClient
from extensions.synology_chat.plugin import synology_chat_plugin


def test_verify_synology_token() -> None:
    assert verify_synology_token("my_token_123", "my_token_123") is True
    assert verify_synology_token("wrong_token", "my_token_123") is False
    assert verify_synology_token("", "my_token_123") is False


def test_parse_synology_webhook() -> None:
    form = {
        "token": "tok1",
        "channel_id": "10",
        "channel_name": "general",
        "username": "admin",
        "text": "@jarvis backup check",
        "post_id": "99",
    }
    parsed = parse_synology_webhook(form)
    assert parsed["token"] == "tok1"
    assert parsed["channel_id"] == "10"
    assert parsed["channel_name"] == "general"
    assert parsed["username"] == "admin"
    assert parsed["text"] == "@jarvis backup check"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(SynologyChatClient, "send_message", return_value={"success": True}):
        res = await synology_chat_plugin.send(
            "https://nas.local/webapi/entry.cgi?token=123", "NAS status OK"
        )
        assert res.is_ok
        assert res.unwrap()["success"] is True
