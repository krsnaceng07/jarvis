"""Unit tests for Buzz extension."""

from __future__ import annotations

import pytest

from extensions.buzz.src.rooms import BuzzRoomManager
from extensions.buzz.plugin import buzz_plugin


def test_buzz_room_manager() -> None:
    mgr = BuzzRoomManager(node_id="node_1")
    mgr.join_room("room_general")
    assert "room_general" in mgr.rooms

    msg = mgr.broadcast("room_general", "Gossip message")
    assert msg.room_id == "room_general"
    assert msg.sender_id == "node_1"
    assert msg.content == "Gossip message"
    assert mgr.is_message_seen(msg.message_id) is True

    mgr.leave_room("room_general")
    assert "room_general" not in mgr.rooms


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await buzz_plugin.send("room_lobby", "Hello mesh")
    assert res.is_ok
    data = res.unwrap()
    assert data["room_id"] == "room_lobby"
    assert data["content"] == "Hello mesh"
