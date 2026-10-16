"""Unit tests for Nextcloud Talk extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.nextcloud_talk.src.signature import verify_nextcloud_signature
from extensions.nextcloud_talk.src.events import parse_talk_event
from extensions.nextcloud_talk.src.client import NextcloudTalkClient
from extensions.nextcloud_talk.plugin import nextcloud_talk_plugin


def test_verify_nextcloud_signature() -> None:
    secret = "secret123"
    body = b'{"token":"room1"}'
    import hmac
    import hashlib

    expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_nextcloud_signature(body, secret, expected_sig) is True
    assert verify_nextcloud_signature(body, secret, f"sha256={expected_sig}") is True
    assert verify_nextcloud_signature(body, secret, "wrong_sig") is False


def test_parse_talk_event() -> None:
    payload = {
        "event": "chat",
        "target": {"token": "room_xyz"},
        "actor": {"id": "user1", "name": "Bob"},
        "object": {"id": 42, "name": "Hello from Talk"},
    }
    parsed = parse_talk_event(payload)
    assert parsed["event"] == "chat"
    assert parsed["room_token"] == "room_xyz"
    assert parsed["actor_name"] == "Bob"
    assert parsed["message"] == "Hello from Talk"
    assert parsed["message_id"] == 42


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(
        NextcloudTalkClient,
        "send_chat_message",
        return_value={"ocs": {"meta": {"statuscode": 200}}},
    ):
        res = await nextcloud_talk_plugin.send("room_xyz", "Test message")
        assert res.is_ok
        assert res.unwrap()["ocs"]["meta"]["statuscode"] == 200
