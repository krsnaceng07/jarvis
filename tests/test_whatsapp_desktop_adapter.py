"""Tests for WhatsApp Desktop application adapter with wrong-recipient guard & exact text verification."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.desktop_automation.applications.whatsapp import WhatsAppDesktopAdapter
from src.desktop_automation.security.recipient_guard import RecipientGuard
from src.desktop_automation.state.active_desktop_context import ActiveDesktopContext
from src.desktop_automation.core.action_contract import ActionEffect


def test_recipient_guard_disambiguation():
    contacts = ["Aakash Sharma", "Aakash Verma", "Bikash Thapa", "John Doe"]

    # Ambiguous query
    unique, sel, matches = RecipientGuard.disambiguate_contact("Aakash", contacts)
    assert unique is False
    assert len(matches) == 2

    # Unique exact query
    unique, sel, matches = RecipientGuard.disambiguate_contact("John Doe", contacts)
    assert unique is True
    assert sel == "John Doe"

    # Unique partial query
    unique, sel, matches = RecipientGuard.disambiguate_contact("Bikash", contacts)
    assert unique is True
    assert sel == "Bikash Thapa"

    # Not found
    unique, sel, matches = RecipientGuard.disambiguate_contact("Zack", contacts)
    assert unique is False
    assert matches == []


def test_recipient_guard_assert_header():
    assert RecipientGuard.assert_active_chat_recipient("Aakash Sharma - WhatsApp", "Aakash Sharma") is True
    assert RecipientGuard.assert_active_chat_recipient("Aakash Sharma", "Aakash") is True
    assert RecipientGuard.assert_active_chat_recipient("Bikash Thapa", "Aakash") is False


@pytest.mark.asyncio
async def test_whatsapp_send_message_verification():
    adapter = WhatsAppDesktopAdapter()
    ctx = ActiveDesktopContext()

    # Mock low-level UI inputs, foreground assertion, and window state
    with patch.object(adapter, "is_foreground", return_value=True), \
         patch.object(adapter, "find_window", return_value=None), \
         patch.object(adapter, "action_open_chat", new_callable=AsyncMock) as mock_open, \
         patch.object(adapter, "get_clipboard_text", return_value="previous_clipboard"), \
         patch.object(adapter, "set_clipboard_text", return_value=True), \
         patch.object(adapter, "hotkey", return_value=True), \
         patch.object(adapter, "press_key", return_value=True):

        mock_open.return_value = MagicMock(ok=True)

        res = await adapter.action_send_message(
            {"recipient": "Aakash", "message": "Hello Aakash!"},
            ctx,
        )

        assert res.ok is True
        assert res.action == "send_message"
        assert res.application == "whatsapp"
        assert res.effect == ActionEffect.CONFIRMED
        assert res.verified is True
        assert res.evidence["recipient"] == "Aakash"
        assert res.evidence["message_length"] == len("Hello Aakash!")
        assert ctx.workflow_stage == "message_sent"
        assert ctx.last_verified_action == "whatsapp_message_sent_to_Aakash"


@pytest.mark.asyncio
async def test_whatsapp_send_empty_validation():
    adapter = WhatsAppDesktopAdapter()
    ctx = ActiveDesktopContext()

    # Empty recipient
    res1 = await adapter.action_send_message({"recipient": "", "message": "hello"}, ctx)
    assert res1.ok is False
    assert "Recipient not specified" in res1.error

    # Empty message
    res2 = await adapter.action_send_message({"recipient": "Aakash", "message": ""}, ctx)
    assert res2.ok is False
    assert "Message text cannot be empty" in res2.error
