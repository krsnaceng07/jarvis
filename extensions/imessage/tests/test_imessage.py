"""Unit tests for iMessage extension."""

from __future__ import annotations

import pytest

from extensions.imessage.plugin import IMessagePlugin, plugin
from extensions.imessage.src.jarvis_imessage.targets import infer_imessage_target_chat_type


def test_imessage_target_inference() -> None:
    assert infer_imessage_target_chat_type("+15551234567") == "direct"
    assert infer_imessage_target_chat_type("user@example.com") == "direct"
    assert infer_imessage_target_chat_type("chat_id:iMessage;+;chat123") == "group"


def test_imessage_plugin_instance() -> None:
    assert plugin.id == "imessage"
    assert plugin.kind == "channel"
    assert isinstance(plugin, IMessagePlugin)


@pytest.mark.asyncio
async def test_imessage_send_unstarted() -> None:
    # Sending before client started returns Err
    res = await plugin.send("+15551234567", "Hello")
    assert res.is_err
    assert "not running" in res.error
