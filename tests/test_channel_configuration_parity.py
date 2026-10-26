"""Unit and integration tests for Telegram bot configuration & live connection parity.

Tests OpenClaw parity:
1. Token validation against Telegram Bot API (/getMe).
2. Canonical ~/.jarvis/config.json persistence.
3. Legacy TelegramState synchronization.
4. Dynamic listener startup without process restart.
5. Inbound message delivery into the live agent host.
6. Agent tool execution (configure_channel, channel_status).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.sessions.tools.channel_tools import (
    CHANNEL_TOOL_DECLARATIONS,
    create_channel_status_tool,
    create_channels_tool,
    create_configure_channel_tool,
    create_whatsapp_login_tool,
)
from src.channels.channel_manager import ChannelManager


@pytest.fixture
def temp_jarvis_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate ~/.jarvis into a temporary directory."""
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def reset_channel_manager() -> ChannelManager:
    """Reset ChannelManager singleton before each test."""
    manager = ChannelManager()
    ChannelManager._instance = manager
    return manager


@pytest.mark.asyncio
async def test_telegram_client_get_me() -> None:
    """Test TelegramClient.get_me method."""
    from extensions.telegram.src.jarvis_telegram.client import TelegramClient

    client = TelegramClient("test_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ok": True,
        "result": {
            "id": 987654321,
            "is_bot": True,
            "first_name": "TestBot",
            "username": "TestJarvisBot",
        },
    }

    with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await client.get_me()
        assert res["ok"] is True
        assert res["result"]["id"] == 987654321
        assert res["result"]["username"] == "TestJarvisBot"
    await client.close()


@pytest.mark.asyncio
async def test_configure_telegram_valid_token(
    temp_jarvis_dir: Path, reset_channel_manager: ChannelManager
) -> None:
    """Test full configuration of Telegram with a valid bot token."""
    mock_get_me_res = {
        "ok": True,
        "result": {
            "id": 123456789,
            "is_bot": True,
            "first_name": "JARVIS Personal",
            "username": "JarvisAiPersonalBot",
        },
    }

    with patch.object(
        reset_channel_manager, "verify_telegram_token", new_callable=AsyncMock
    ) as mock_verify:
        mock_verify.return_value = mock_get_me_res

        # Mock the listener start to avoid network loop
        with patch.object(
            reset_channel_manager, "start_channel_listener", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {"ok": True, "status": "listening"}

            result = await reset_channel_manager.configure_telegram(
                bot_token="123456:ABC-DEF_valid_token",
                dm_policy="open",
                allow_from=["*"],
            )

            assert result["ok"] is True
            assert result["bot_id"] == 123456789
            assert result["bot_username"] == "@JarvisAiPersonalBot"
            assert result["status"] == "connected_and_listening"
            assert result["listener_active"] is True

    # Verify ~/.jarvis/config.json was properly written
    cfg_file = temp_jarvis_dir / "config.json"
    assert cfg_file.exists()
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "channels" in cfg
    assert "telegram" in cfg["channels"]
    tg_cfg = cfg["channels"]["telegram"]
    assert tg_cfg["enabled"] is True
    assert tg_cfg["botToken"] == "123456:ABC-DEF_valid_token"
    assert tg_cfg["dmPolicy"] == "open"
    assert tg_cfg["botId"] == 123456789
    assert tg_cfg["botUsername"] == "JarvisAiPersonalBot"


@pytest.mark.asyncio
async def test_telegram_listener_start_is_idempotent(
    temp_jarvis_dir: Path, reset_channel_manager: ChannelManager
) -> None:
    """A duplicate auto-start must not re-open the same Telegram poller."""
    cfg_file = temp_jarvis_dir / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "channels": {
                    "telegram": {
                        "enabled": True,
                        "botToken": "123456:ABC-DEF_valid_token",
                        "pollingIntervalSec": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    class FakePlugin:
        def __init__(self) -> None:
            self.reconfigures = 0
            self.listens = 0

        def reconfigure(
            self, config: dict[str, Any], callback: Any = None, auto_listen: bool = True
        ) -> bool:
            self.reconfigures += 1
            self.callback = callback
            self.config = config
            assert auto_listen is False, "listener start must go through listen()"
            return True

        async def listen(self, callback: Any) -> None:
            self.listens += 1

    plugin = FakePlugin()
    reset_channel_manager._channel_plugins["telegram"] = plugin

    first = await reset_channel_manager.start_channel_listener("telegram")
    second = await reset_channel_manager.start_channel_listener("telegram")

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["status"] == "already_listening"
    assert plugin.listens == 1
    assert reset_channel_manager._active_listeners["telegram"] is True


@pytest.mark.asyncio
async def test_concurrent_listener_start_does_not_start_twice(
    temp_jarvis_dir: Path, reset_channel_manager: ChannelManager
) -> None:
    cfg_file = temp_jarvis_dir / "config.json"
    cfg_file.write_text(
        json.dumps({"channels": {"telegram": {"enabled": True, "botToken": "test-token"}}}),
        encoding="utf-8",
    )

    entered_listen = asyncio.Event()
    finish_listen = asyncio.Event()

    class FakePlugin:
        def __init__(self) -> None:
            self.calls = 0

        async def listen(self, callback: Any) -> None:
            self.calls += 1
            entered_listen.set()
            await finish_listen.wait()

    plugin = FakePlugin()
    reset_channel_manager._channel_plugins["telegram"] = plugin
    first_start = asyncio.create_task(reset_channel_manager.start_channel_listener("telegram"))
    await entered_listen.wait()

    duplicate_start = await reset_channel_manager.start_channel_listener("telegram")
    finish_listen.set()
    first_result = await first_start

    assert duplicate_start["ok"] is False
    assert duplicate_start["status"] == "starting"
    assert first_result["ok"] is True
    assert plugin.calls == 1
    assert reset_channel_manager._active_listeners["telegram"] is True


@pytest.mark.asyncio
async def test_configure_telegram_invalid_token(
    temp_jarvis_dir: Path, reset_channel_manager: ChannelManager
) -> None:
    """Test rejection when Telegram API reports an invalid bot token."""
    mock_verify_res = {
        "ok": False,
        "error": "Unauthorized: Telegram Bot API rejected the provided token.",
    }

    with patch.object(
        reset_channel_manager, "verify_telegram_token", new_callable=AsyncMock
    ) as mock_verify:
        mock_verify.return_value = mock_verify_res

        result = await reset_channel_manager.configure_telegram(
            bot_token="invalid_bad_token_123",
            dm_policy="open",
        )

        assert result["ok"] is False
        assert "verification failed" in result["error"]

    # Verify ~/.jarvis/config.json was NOT corrupted with invalid token
    cfg_file = temp_jarvis_dir / "config.json"
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "telegram" not in cfg.get("channels", {})


@pytest.mark.asyncio
async def test_configure_channel_tool_execution(
    temp_jarvis_dir: Path, reset_channel_manager: ChannelManager
) -> None:
    """Test execution of configure_channel tool by agent."""
    tool = create_configure_channel_tool()

    # Success case
    with patch.object(
        reset_channel_manager, "configure_channel", new_callable=AsyncMock
    ) as mock_conf:
        mock_conf.return_value = {
            "ok": True,
            "message": "Successfully configured and verified Telegram bot @JarvisBot.",
            "bot_username": "@JarvisBot",
            "bot_id": 123456,
            "status": "connected_and_listening",
        }

        res = await tool["execute"](
            "call_1",
            {"channel": "telegram", "token": "99999:ABC_XYZ", "dm_policy": "open"},
        )
        assert "Successfully configured" in res["result"]
        assert res["data"]["bot_username"] == "@JarvisBot"

    # Error case: missing token
    res_missing = await tool["execute"]("call_2", {"channel": "telegram", "token": ""})
    assert "Error: 'token' parameter is required." in res_missing["content"][0]["text"]


@pytest.mark.asyncio
async def test_channel_status_tool_execution(
    temp_jarvis_dir: Path, reset_channel_manager: ChannelManager
) -> None:
    """Test channel_status tool execution."""
    cfg_file = temp_jarvis_dir / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "channels": {
                    "telegram": {
                        "enabled": True,
                        "botToken": "test_tok",
                        "botUsername": "MyBot",
                        "botName": "Jarvis",
                        "dmPolicy": "open",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    tool = create_channel_status_tool()
    res = await tool["execute"]("call_status", {"channel": "telegram"})
    assert res["data"]["channel"] == "telegram"
    assert res["data"]["configured"] is True
    assert res["data"]["bot_username"] == "MyBot"


@pytest.mark.asyncio
async def test_inbound_telegram_message_dispatch(
    reset_channel_manager: ChannelManager,
) -> None:
    """Test that incoming messages from Telegram route into ChannelTurnRunner without desktop leakage."""
    mock_live_host = MagicMock()
    reset_channel_manager.set_live_host(mock_live_host)

    handler = reset_channel_manager._create_inbound_handler("telegram")
    inbound_event = {
        "kind": "message",
        "chat_id": "12345",
        "from_id": "12345",
        "text": "Hello JARVIS, what is the weather?",
        "target": "telegram:12345",
    }

    with patch.object(
        reset_channel_manager,
        "_run_channel_turn",
        new_callable=AsyncMock,
    ) as mock_run_turn:
        handler(inbound_event)
        await asyncio.sleep(0.05)

        # Verify channel turn runner was invoked directly with inbound payload
        mock_run_turn.assert_called_once_with("telegram", inbound_event)
        # Verify desktop HUD/speaker was NOT invoked (strict channel reply isolation)
        mock_live_host._on_text_command.assert_not_called()


def test_channel_tool_declarations_schema() -> None:
    """Verify tool schema definitions match OpenClaw and Gemini Live expectations."""
    names = {d["name"] for d in CHANNEL_TOOL_DECLARATIONS}
    assert "configure_channel" in names
    assert "channel_status" in names
    assert "channels" in names
    assert "whatsapp_login" in names

    cfg_decl = next(d for d in CHANNEL_TOOL_DECLARATIONS if d["name"] == "configure_channel")
    assert "channel" in cfg_decl["parameters"]["properties"]
    assert "token" in cfg_decl["parameters"]["properties"]
    assert "dm_policy" in cfg_decl["parameters"]["properties"]
    assert cfg_decl["parameters"]["required"] == ["channel", "token"]


def test_whatsapp_plugin_qr_rendering() -> None:
    """Test QR PNG data URL and ASCII art rendering for WhatsApp login."""
    from extensions.whatsapp.plugin import WhatsAppPlugin

    payload = "1@dummy_whatsapp_qr_pairing_string,test_pubkey,test_adv"
    data_url = WhatsAppPlugin._render_qr_data_url(payload)
    assert data_url.startswith("data:image/png;base64,")
    assert len(data_url) > 100

    ascii_qr = WhatsAppPlugin._render_ascii_qr(payload)
    assert "\n" in ascii_qr
    assert len(ascii_qr) > 50


@pytest.mark.asyncio
async def test_whatsapp_login_tool_returns_qr_markdown(
    reset_channel_manager: ChannelManager,
) -> None:
    """Test whatsapp_login tool generates and embeds QR markdown image for phone scanning."""
    mock_login_res = {
        "ok": True,
        "status": "qr_ready",
        "qr": "dummy_qr",
        "qr_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
        "ascii_qr": "██████",
    }

    with patch.object(
        reset_channel_manager, "login_whatsapp", new_callable=AsyncMock
    ) as mock_login:
        mock_login.return_value = mock_login_res
        tool = create_whatsapp_login_tool()
        res = await tool["execute"]("call_wa_login", {"action": "start"})

        assert mock_login.called
        text = res["content"][0]["text"]
        assert "![WhatsApp QR](data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==)" in text
        assert "Linked Devices" in text


@pytest.mark.asyncio
async def test_channels_tool_login_whatsapp(
    reset_channel_manager: ChannelManager,
) -> None:
    """Test unified channels tool with action='login' and channel='whatsapp' returns QR."""
    mock_login_res = {
        "ok": True,
        "status": "qr_ready",
        "qr_data_url": "data:image/png;base64,test_qr_123",
        "ascii_qr": "████",
    }

    with patch.object(
        reset_channel_manager, "login_whatsapp", new_callable=AsyncMock
    ) as mock_login:
        mock_login.return_value = mock_login_res
        tool = create_channels_tool()
        res = await tool["execute"]("call_channels_wa", {"action": "login", "channel": "whatsapp"})

        assert mock_login.called
        text = res["content"][0]["text"]
        assert "![WhatsApp QR](data:image/png;base64,test_qr_123)" in text

