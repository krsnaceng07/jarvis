"""Unit tests for Zalo extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.zalo.src.events import parse_zalo_webhook
from extensions.zalo.src.client import ZaloClient
from extensions.zalo.plugin import zalo_plugin


def test_parse_zalo_webhook() -> None:
    payload = {
        "event_name": "user_send_text",
        "app_id": "app_123",
        "oa_id": "oa_456",
        "sender": {"id": "user_789"},
        "recipient": {"id": "oa_456"},
        "message": {"text": "Xin chao", "msg_id": "msg_001"},
    }
    parsed = parse_zalo_webhook(payload)
    assert parsed["event_name"] == "user_send_text"
    assert parsed["sender_id"] == "user_789"
    assert parsed["text"] == "Xin chao"
    assert parsed["msg_id"] == "msg_001"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(ZaloClient, "send_text", return_value={"error": 0, "message": "Success"}):
        res = await zalo_plugin.send("user_789", "Hello Zalo")
        assert res.is_ok
        assert res.unwrap()["error"] == 0
