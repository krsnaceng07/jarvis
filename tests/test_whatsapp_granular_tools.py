"""Unit tests for WhatsApp granular tools in desktop automation."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.desktop_automation.providers.base_provider import (
    ApplicationState,
    CompletionStatus,
    ContactCandidate,
    ProviderActionResult,
)
from src.desktop_automation.tools.whatsapp_tools import (
    whatsapp_get_state_tool,
    whatsapp_open_chat_tool,
    whatsapp_open_tool,
    whatsapp_search_contact_tool,
    whatsapp_send_message_tool,
    whatsapp_verify_message_tool,
)


@pytest.mark.asyncio
async def test_whatsapp_get_state_tool():
    """Verify whatsapp_get_state_tool formats state correctly."""
    mock_state = ApplicationState(
        app_id="whatsapp",
        is_running=True,
        is_minimized=True,
        is_foreground=False,
        hwnd=66708,
        pid=5928,
        window_title="WhatsApp",
        active_chat="Krishna",
    )
    with patch("src.desktop_automation.tools.whatsapp_tools._get_whatsapp_provider") as mock_get:
        mock_provider = MagicMock()
        mock_provider.get_state = AsyncMock(return_value=mock_state)
        mock_get.return_value = mock_provider

        output = await whatsapp_get_state_tool({})
        assert "Running=True" in output
        assert "Minimized=True" in output
        assert "Foreground=False" in output
        assert "Active Chat='Krishna'" in output


@pytest.mark.asyncio
async def test_whatsapp_send_message_tool_empty_validation():
    """Verify whatsapp_send_message_tool validates recipient and text."""
    # Missing recipient
    out1 = await whatsapp_send_message_tool({"message": "hi"})
    assert "Error: 'recipient' parameter is required" in out1

    # Missing message
    out2 = await whatsapp_send_message_tool({"recipient": "Krishna"})
    assert "Error: 'message' text cannot be empty" in out2


@pytest.mark.asyncio
async def test_whatsapp_send_message_tool_execution():
    """Verify whatsapp_send_message_tool calls provider and returns success."""
    mock_res = ProviderActionResult(
        ok=True,
        action="send_message",
        application="whatsapp",
        status=CompletionStatus.COMPLETED_VERIFIED,
        output_text="SUCCESS: Message sent to 'Krishna Kushwaha'. [TASK FULFILLED]",
    )
    with patch("src.desktop_automation.tools.whatsapp_tools._get_whatsapp_provider") as mock_get:
        mock_provider = MagicMock()
        mock_provider.send_message = AsyncMock(return_value=mock_res)
        mock_get.return_value = mock_provider

        out = await whatsapp_send_message_tool({
            "recipient": "Krishna Kushwaha",
            "message": "Hello from OpenClaw architecture!",
        })
        assert "SUCCESS: Message sent to 'Krishna Kushwaha'" in out
        assert "[TASK FULFILLED]" in out
        mock_provider.send_message.assert_awaited_once_with(
            "Krishna Kushwaha",
            "Hello from OpenClaw architecture!",
        )


@pytest.mark.asyncio
async def test_whatsapp_search_and_open_chat():
    """Verify search contact and open chat tools."""
    mock_candidates = [ContactCandidate(name="Krishna Kushwaha", confidence=1.0)]
    mock_open_res = ProviderActionResult(
        ok=True,
        action="open_chat",
        application="whatsapp",
        output_text="Opened WhatsApp chat with 'Krishna Kushwaha'.",
    )

    with patch("src.desktop_automation.tools.whatsapp_tools._get_whatsapp_provider") as mock_get:
        mock_provider = MagicMock()
        mock_provider.search_contacts = AsyncMock(return_value=mock_candidates)
        mock_provider.open_chat = AsyncMock(return_value=mock_open_res)
        mock_get.return_value = mock_provider

        search_out = await whatsapp_search_contact_tool({"query": "Krishna"})
        assert "Found matching contacts: 'Krishna Kushwaha'" in search_out

        open_out = await whatsapp_open_chat_tool({"recipient": "Krishna Kushwaha"})
        assert "Opened WhatsApp chat with 'Krishna Kushwaha'" in open_out
