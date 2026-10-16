"""Unit tests for WhatsApp Provider Model and Application Session Manager."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.desktop_automation.providers.base_provider import (
    ApplicationState,
    BaseMessagingProvider,
    CompletionStatus,
    ContactCandidate,
    ProviderActionResult,
)
from src.desktop_automation.providers.registry import ProviderRegistry
from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider
from src.desktop_automation.state.session_manager import ApplicationSessionManager


def test_provider_registry_singleton():
    """Verify ProviderRegistry is a singleton and registers default providers."""
    registry = ProviderRegistry.get_instance()
    assert registry is not None
    assert "whatsapp" in registry.list_providers()

    provider = registry.get_provider("whatsapp")
    assert provider is not None
    assert isinstance(provider, BaseMessagingProvider)
    assert provider.app_id == "whatsapp"


def test_application_session_manager():
    """Verify ApplicationSessionManager updates and preserves application sessions."""
    manager = ApplicationSessionManager.get_instance()
    session = manager.update_session(
        app_id="whatsapp",
        app_name="WhatsApp Desktop",
        process_id=5928,
        window_id=66708,
        window_title="WhatsApp",
        is_minimized=False,
        is_foreground=True,
        active_chat="Krishna",
    )
    assert session.app_id == "whatsapp"
    assert session.active_chat == "Krishna"
    assert session.is_fresh() is True

    retrieved = manager.get_session("whatsapp")
    assert retrieved is not None
    assert retrieved.process_id == 5928


@pytest.mark.asyncio
async def test_whatsapp_provider_foreground_guard():
    """Verify WhatsAppDesktopProvider aborts typing when window cannot be focused."""
    provider = WhatsAppDesktopProvider()

    # Mock adapter to simulate WhatsApp failing to acquire foreground
    with patch.object(provider.adapter, "is_foreground", return_value=False), \
         patch.object(provider.adapter, "ensure_running_and_focused", return_value=False):
        res = await provider.send_message("Krishna", "Hello World")
        assert res.ok is False
        assert res.status == CompletionStatus.BLOCKED
        assert "minimized or could not be brought to the active foreground" in res.error


@pytest.mark.asyncio
async def test_whatsapp_provider_send_success():
    """Verify WhatsAppDesktopProvider sends message when foreground is verified."""
    provider = WhatsAppDesktopProvider()

    mock_res = MagicMock()
    mock_res.ok = True
    mock_res.error = None
    mock_res.evidence = {"recipient": "Krishna", "status": "delivered"}
    mock_res.output_text = "Delivered to Krishna"

    with patch.object(provider.adapter, "is_foreground", return_value=True), \
         patch.object(provider.adapter, "action_send_message", new_callable=AsyncMock, return_value=mock_res):
        res = await provider.send_message("Krishna", "Hello World")
        assert res.ok is True
        assert res.status == CompletionStatus.COMPLETED_VERIFIED
        assert "TASK FULFILLED" in res.output_text
