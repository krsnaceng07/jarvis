"""Tests for Wave 18 — Gateway WebSocket + Live State."""

from __future__ import annotations

import json
import pytest

from src.gateway.live_state import GLOBAL_GATEWAY_LIVE_STATE
from src.gateway.ws_server import GatewayWSConnection


@pytest.mark.asyncio
async def test_gateway_live_state_and_subscriptions():
    sent_messages: list[str] = []

    async def mock_send(text: str) -> None:
        sent_messages.append(text)

    conn = GatewayWSConnection(mock_send, "conn-1")

    # Handle subscribe
    sub_msg = json.dumps({"jsonrpc": "2.0", "method": "subscribe", "params": {"topic": "agent.event"}, "id": 1})
    await conn.handle_message(sub_msg, lambda r: None)

    assert len(sent_messages) == 1
    res = json.loads(sent_messages[0])
    assert res["result"] == {"subscribed": "agent.event"}

    # Broadcast event
    await GLOBAL_GATEWAY_LIVE_STATE.emit_event("agent.event", {"status": "started"})
    assert len(sent_messages) == 2
    event_frame = json.loads(sent_messages[1])
    assert event_frame["method"] == "gateway.event"
    assert event_frame["params"]["topic"] == "agent.event"

    # Cleanup
    conn.on_close()


@pytest.mark.asyncio
async def test_gateway_subscriptions_are_cleared_on_close():
    sent_messages: list[str] = []

    async def mock_send(text: str) -> None:
        sent_messages.append(text)

    conn = GatewayWSConnection(mock_send, "conn-close")
    await conn.handle_message(
        json.dumps({"jsonrpc": "2.0", "method": "subscribe", "params": {"topic": "agent.event"}, "id": 2}),
        lambda r: None,
    )

    assert len(sent_messages) == 1

    conn.on_close()
    await GLOBAL_GATEWAY_LIVE_STATE.emit_event("agent.event", {"status": "stopped"})

    assert len(sent_messages) == 1


@pytest.mark.asyncio
async def test_gateway_handshake_tracks_live_state_session_and_channel():
    sent_messages: list[str] = []

    async def mock_send(text: str) -> None:
        sent_messages.append(text)

    conn = GatewayWSConnection(mock_send, "conn-live")
    ok = await conn.handle_handshake(
        json.dumps({
            "jsonrpc": "2.0",
            "method": "connect",
            "params": {
                "auth": {"token": "abc123"},
                "role": "client",
                "identity": {"channel": "local", "session_id": "session-42"},
            },
            "id": 3,
        }),
        "abc123",
    )

    assert ok is True
    assert GLOBAL_GATEWAY_LIVE_STATE.active_sessions["session-42"]["metadata"]["role"] == "client"
    assert GLOBAL_GATEWAY_LIVE_STATE.channel_status["local"] is True

    conn.on_close()
    assert "session-42" not in GLOBAL_GATEWAY_LIVE_STATE.active_sessions
    assert GLOBAL_GATEWAY_LIVE_STATE.channel_status["local"] is False


def test_gateway_live_state_tracks_running_tasks() -> None:
    state = GLOBAL_GATEWAY_LIVE_STATE
    state.set_task_running("task-1", True)
    assert state.is_task_running("task-1") is True

    state.set_task_running("task-1", False)
    assert state.is_task_running("task-1") is False
