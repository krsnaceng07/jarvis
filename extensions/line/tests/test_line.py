"""Unit tests for LINE extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.line.src.signature import verify_line_signature
from extensions.line.src.events import parse_line_events
from extensions.line.src.client import LineClient
from extensions.line.plugin import line_plugin


def test_verify_line_signature() -> None:
    secret = "test_secret_123"
    body = b'{"events":[]}'
    # Expected signature for secret and body
    import hmac
    import hashlib
    import base64

    expected_sig = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    assert verify_line_signature(body, secret, expected_sig) is True
    assert verify_line_signature(body, secret, "invalid_sig") is False
    assert verify_line_signature(body, "", expected_sig) is False


def test_parse_line_events() -> None:
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rep123",
                "source": {"type": "user", "userId": "u123"},
                "message": {"type": "text", "text": "Hello Jarvis"},
                "timestamp": 123456789,
            }
        ]
    }
    events = parse_line_events(payload)
    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "message"
    assert ev["reply_token"] == "rep123"
    assert ev["user_id"] == "u123"
    assert ev["text"] == "Hello Jarvis"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(LineClient, "push_text", return_value={"ok": True}):
        res = await line_plugin.send("u123", "Hello")
        assert res.is_ok
        assert res.unwrap()["ok"] is True
