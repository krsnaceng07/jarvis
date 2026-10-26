"""Test channel reply isolation and zero-leakage contract.

Verifies:
1. Inbound channel messages NEVER leak into desktop HUD or speakers (_on_text_command).
2. Replies are strictly routed back to the originating channel/conversation via plugin.send.
3. Event loops are safely provided or managed without dropping turns.
4. Channel configuration handles multiple channels (telegram, discord, slack, etc.).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.channels.channel_manager import ChannelManager


class DummyChannelPlugin:
    def __init__(self, channel_id: str) -> None:
        self.id = channel_id
        self.sent_messages: list[tuple[str, dict[str, Any]]] = []

    async def send(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.sent_messages.append((target, payload))
        return {"ok": True, "message_id": f"msg_{len(self.sent_messages)}"}

    async def listen(self, callback: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_channel_reply_never_diverts_to_desktop_hud_or_speaker():
    """Verify that inbound channel events NEVER invoke _on_text_command on live_host."""
    mgr = ChannelManager()
    plugin = DummyChannelPlugin("telegram")
    mgr.register_plugin("telegram", plugin)

    mock_live_host = MagicMock()
    mock_live_host._loop = None  # Explicitly simulate missing/stopped host loop
    mock_live_host._on_text_command = MagicMock()

    mgr.set_live_host(mock_live_host)

    # Inbound message handler
    handler = mgr._create_inbound_handler("telegram")

    with patch.object(
        mgr,
        "_run_channel_turn",
        new_callable=AsyncMock,
    ) as mock_run_turn:
        inbound = {
            "kind": "message",
            "chat_id": "12345678",
            "from_id": "87654321",
            "text": "Hello Jarvis from Telegram!",
        }
        handler(inbound)

        # Give event loop a brief moment to process threadsafe dispatch
        await asyncio.sleep(0.05)

        # 1. Desktop HUD / voice handler was NEVER touched
        mock_live_host._on_text_command.assert_not_called()

        # 2. Channel turn runner was invoked directly with inbound payload
        mock_run_turn.assert_called_once_with("telegram", inbound)


@pytest.mark.asyncio
async def test_channel_turn_delivery_routes_to_origin_channel():
    """Verify that _run_channel_turn delivers strictly to the origin channel plugin."""
    mgr = ChannelManager()
    tg_plugin = DummyChannelPlugin("telegram")
    mgr.register_plugin("telegram", tg_plugin)

    inbound = {
        "kind": "message",
        "chat_id": "chat_999",
        "from_id": "user_888",
        "text": "Test message",
        "message_id": "msg_001",
    }

    # Mock agent turn to return a synthetic response
    async def mock_agent_turn(assembled: Any, delivery: Any) -> str:
        return "Reply specifically for chat_999"

    with patch.object(mgr, "_dispatch_channel_agent_turn", side_effect=mock_agent_turn):
        await mgr._run_channel_turn("telegram", inbound)

    # Verify plugin.send was invoked with target and origin route
    assert len(tg_plugin.sent_messages) == 1
    target, payload = tg_plugin.sent_messages[0]
    assert "chat_999" in target
    assert payload["text"] == "Reply specifically for chat_999"
    assert payload["reply_to"] == "msg_001"
    assert payload["origin_route"]["channel"] == "telegram"


@pytest.mark.asyncio
async def test_channel_turn_cross_channel_isolation():
    """Verify telegram and discord messages stay completely isolated."""
    mgr = ChannelManager()
    tg_plugin = DummyChannelPlugin("telegram")
    discord_plugin = DummyChannelPlugin("discord")
    mgr.register_plugin("telegram", tg_plugin)
    mgr.register_plugin("discord", discord_plugin)

    async def mock_agent_turn(assembled: Any, delivery: Any) -> str:
        return f"Echo {assembled.message.channel_id}: {assembled.message.text}"

    with patch.object(mgr, "_dispatch_channel_agent_turn", side_effect=mock_agent_turn):
        await mgr._run_channel_turn(
            "telegram",
            {"kind": "message", "chat_id": "tg_chat", "text": "Hi TG", "message_id": "tg_1"},
        )
        await mgr._run_channel_turn(
            "discord",
            {"kind": "message", "chat_id": "dc_channel", "text": "Hi DC", "message_id": "dc_1"},
        )

    assert len(tg_plugin.sent_messages) == 1
    assert "tg_chat" in tg_plugin.sent_messages[0][0]
    assert tg_plugin.sent_messages[0][1]["text"] == "Echo telegram: Hi TG"

    assert len(discord_plugin.sent_messages) == 1
    assert "dc_channel" in discord_plugin.sent_messages[0][0]
    assert discord_plugin.sent_messages[0][1]["text"] == "Echo discord: Hi DC"


@pytest.mark.asyncio
async def test_generic_channel_configuration():
    """Verify non-telegram channels can be configured generically."""
    mgr = ChannelManager()

    with (
        patch("src.channels.channel_manager._write_canonical_config"),
        patch(
            "src.channels.channel_manager._read_canonical_config",
            return_value={"channels": {}},
        ),
        patch.object(
            mgr,
            "start_channel_listener",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ),
    ):
        res = await mgr.configure_channel("discord", token="test_discord_token", dm_policy="open")
        assert res["ok"] is True
        assert res["channel"] == "discord"
        assert res["status"] == "connected_and_listening"


@pytest.mark.asyncio
async def test_telegram_turn_leaves_voice_synthesis_to_plugin():
    """The channel manager must not synthesize TTS before handing off to the plugin.

    Manager-side synthesis delayed every reply; the owning plugin now sends text
    first and synthesizes the voice note afterwards.
    """
    mgr = ChannelManager()
    tg_plugin = DummyChannelPlugin("telegram")
    mgr.register_plugin("telegram", tg_plugin)

    inbound = {
        "kind": "message",
        "chat_id": "tg_voice_chat",
        "from_id": "user_voice",
        "text": "Tell me a joke",
        "message_id": "msg_joke",
    }

    async def mock_agent_turn(assembled: Any, delivery: Any) -> str:
        return "Why did the computer catch a cold? Because it had a bad Windows."

    with (
        patch.object(mgr, "_dispatch_channel_agent_turn", side_effect=mock_agent_turn),
        patch(
            "src.talk.speech_synthesizer.synthesize_speech_wav_async",
            new_callable=AsyncMock,
            return_value=b"RIFFdummywavbytes",
        ) as mock_synth,
    ):
        await mgr._run_channel_turn("telegram", inbound)

    assert len(tg_plugin.sent_messages) == 1
    target, payload = tg_plugin.sent_messages[0]
    assert "tg_voice_chat" in target
    assert payload["text"] == "Why did the computer catch a cold? Because it had a bad Windows."
    assert "voice_bytes" not in payload
    mock_synth.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_plugin_dual_modality_delivery():
    """Verify TelegramChannelPlugin.send transmits both text message and voice note."""
    from extensions.telegram.src.jarvis_telegram.plugin import TelegramChannelPlugin

    plugin = TelegramChannelPlugin()
    mock_client = AsyncMock()
    mock_client.send_message.return_value = {"ok": True, "result": {"message_id": 101}}
    mock_client.send_voice.return_value = {"ok": True, "result": {"message_id": 102}}
    plugin.client = mock_client

    message = {
        "text": "Hello, this is a dual modality reply.",
        "voice_bytes": b"RIFFfakevoice",
        "reply_to": "42",
    }

    res = await plugin.send("telegram:999888", message)
    assert res.is_ok
    mock_client.send_message.assert_called_once()
    assert (
        mock_client.send_message.call_args.kwargs["text"] == "Hello, this is a dual modality reply."
    )
    mock_client.send_voice.assert_called_once()
    assert mock_client.send_voice.call_args.kwargs["voice_bytes"] == b"RIFFfakevoice"


@pytest.mark.asyncio
async def test_telegram_plugin_sends_text_before_synthesizing_voice():
    """Telegram text goes out first; TTS runs only after the reply landed."""
    from extensions.telegram.src.jarvis_telegram.plugin import TelegramChannelPlugin

    plugin = TelegramChannelPlugin()
    events: list[str] = []
    mock_client = AsyncMock()

    async def _send_message(**_kwargs: Any) -> dict[str, Any]:
        events.append("text")
        return {"ok": True, "result": {"message_id": 201}}

    mock_client.send_message.side_effect = _send_message
    mock_client.send_voice.return_value = {"ok": True, "result": {"message_id": 202}}
    plugin.client = mock_client

    async def _synthesize(_text: str) -> bytes:
        events.append("synth")
        return b"RIFFlatevoice"

    with patch(
        "src.talk.speech_synthesizer.synthesize_speech_wav_async",
        side_effect=_synthesize,
    ):
        res = await plugin.send("telegram:999888", {"text": "Fast reply please."})

    assert res.is_ok
    assert events == ["text", "synth"]
    mock_client.send_voice.assert_called_once()


def test_speech_text_cleaning():
    """Verify markdown and noisy tokens are stripped for spoken synthesis."""
    from src.talk.speech_synthesizer import clean_text_for_speech

    raw = (
        "# Title\n"
        "Here is **bold** text and `inline_code`.\n"
        "```python\nprint('hello')\n```\n"
        "Check [this link](https://example.com) for details."
    )
    cleaned = clean_text_for_speech(raw)
    assert "Title" in cleaned
    assert "bold text and inline_code" in cleaned
    assert "[Code snippet omitted]" in cleaned
    assert "https://" not in cleaned
    assert "#" not in cleaned
    assert "*" not in cleaned
