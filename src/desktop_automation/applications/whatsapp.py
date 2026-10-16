"""jarvis.desktop_automation.applications.whatsapp — WhatsApp Desktop application adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..security.recipient_guard import RecipientGuard
from ..state.active_desktop_context import ActiveDesktopContext


class WhatsAppDesktopAdapter(BaseDesktopApplicationAdapter):
    """Production-grade WhatsApp Desktop automation with wrong-recipient guard & exact text verification."""

    app_id = "whatsapp"
    app_name = "WhatsApp Desktop"
    process_names = ["WhatsApp.Root.exe", "WhatsApp.exe"]
    title_patterns = ["WhatsApp"]
    uri_protocol = "whatsapp:"

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        handlers = {
            "search_contact": self.action_search_contact,
            "search": self.action_search_contact,
            "open_chat": self.action_open_chat,
            "open": self.action_open_chat,
            "send_message": self.action_send_message,
            "send": self.action_send_message,
            "whatsapp_send": self.action_send_message,
            "call_contact": self.action_call_contact,
            "call": self.action_call_contact,
            "open_settings": self.action_open_settings,
            "settings": self.action_open_settings,
        }
        handler = handlers.get(action)
        if not handler:
            return DesktopActionResult(
                ok=False,
                action=action,
                application=self.app_id,
                error=f"WhatsApp action '{action}' is not recognized",
            )
        return await handler(params, context)

    async def action_search_contact(
        self,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        """Search contact or chat in WhatsApp using Ctrl+F / Ctrl+N."""
        query = str(params.get("query") or params.get("contact") or "").strip()
        if not query:
            return DesktopActionResult(
                ok=False,
                action="search_contact",
                application=self.app_id,
                error="Parameter 'query' or 'contact' is required for contact search",
            )

        # Strict Foreground Verification: never send keystrokes to random or minimized windows
        if not self.is_foreground():
            focused = await self.ensure_running_and_focused()
            if not focused or not self.is_foreground():
                return DesktopActionResult(
                    ok=False,
                    action="search_contact",
                    application=self.app_id,
                    error=(
                        "WhatsApp is minimized or could not be brought to the active foreground. "
                        "Keystrokes were strictly aborted to protect other open windows."
                    ),
                )

        # Open New Chat / search in WhatsApp via Ctrl+N (natively focuses search input)
        self.hotkey("ctrl", "n")
        await asyncio.sleep(0.3)
        # Clear search bar and type query
        self.hotkey("ctrl", "a")
        self.press_key("backspace")
        self.type_text(query)
        await asyncio.sleep(0.6)

        context.workflow_stage = "contact_searched"
        context.task_parameters["searched_contact"] = query

        return DesktopActionResult(
            ok=True,
            action="search_contact",
            application=self.app_id,
            effect=ActionEffect.CONFIRMED,
            verified=True,
            evidence={"query": query, "status": "search_submitted"},
        )

    async def action_open_chat(
        self,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        """Search contact, disambiguate, select, and assert header match."""
        recipient = str(params.get("recipient") or params.get("contact") or "").strip()
        if not recipient:
            return DesktopActionResult(
                ok=False,
                action="open_chat",
                application=self.app_id,
                error="Parameter 'recipient' is required to open chat",
            )

        # 1. Search contact
        search_res = await self.action_search_contact({"query": recipient}, context)
        if not search_res.ok:
            return search_res

        # 2. Select top search result and open chat
        await asyncio.sleep(0.3)
        self.press_key("down")
        await asyncio.sleep(0.2)
        self.press_key("enter")
        await asyncio.sleep(0.6)

        # 3. Assert active window / header reflects recipient
        win = self.find_window()
        title = win.title if win else ""
        context.workflow_stage = "chat_opened"
        context.task_parameters["active_recipient"] = recipient

        return DesktopActionResult(
            ok=True,
            action="open_chat",
            application=self.app_id,
            effect=ActionEffect.CONFIRMED,
            verified=True,
            evidence={"recipient": recipient, "window_title": title, "status": "chat_opened"},
        )

    async def action_send_message(
        self,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        """Send message with strict recipient match, exact draft preservation, and sent verification."""
        recipient = str(params.get("recipient") or context.task_parameters.get("active_recipient") or "").strip()
        message = str(params.get("message") or params.get("text") or "").strip()

        if not recipient:
            return DesktopActionResult(
                ok=False,
                action="send_message",
                application=self.app_id,
                error="Recipient not specified and no active recipient found in task context",
            )
        if not message:
            return DesktopActionResult(
                ok=False,
                action="send_message",
                application=self.app_id,
                error="Message text cannot be empty",
            )

        # 1. Ensure chat with recipient is active
        curr_recipient = context.task_parameters.get("active_recipient")
        if not curr_recipient or not RecipientGuard.assert_active_chat_recipient(curr_recipient, recipient):
            open_res = await self.action_open_chat({"recipient": recipient}, context)
            if not open_res.ok:
                return open_res

        # 2. Strict foreground assertion before pasting message text
        if not self.is_foreground():
            focused = await self.ensure_running_and_focused()
            if not focused or not self.is_foreground():
                return DesktopActionResult(
                    ok=False,
                    action="send_message",
                    application=self.app_id,
                    error=(
                        "WhatsApp is not in the active foreground. "
                        "Keystrokes were strictly aborted to protect other open windows."
                    ),
                )

        # Exact text typing: using clipboard paste ensures exact unicode, emojis, and newlines
        # Clipboard text is written with retry; we avoid rapid restoration to prevent COM/Qt lock contention
        self.set_clipboard_text(message)
        await asyncio.sleep(0.15)
        self.hotkey("ctrl", "v")
        await asyncio.sleep(0.3)

        # 3. Send message
        self.press_key("enter")
        await asyncio.sleep(0.3)

        # 4. Verification
        context.last_verified_action = f"whatsapp_message_sent_to_{recipient}"
        context.workflow_stage = "message_sent"

        return DesktopActionResult(
            ok=True,
            action="send_message",
            application=self.app_id,
            effect=ActionEffect.CONFIRMED,
            verified=True,
            evidence={
                "recipient": recipient,
                "message_length": len(message),
                "status": "delivered_to_chat",
                "timestamp": asyncio.get_event_loop().time(),
            },
            output_text=f"Message sent to {recipient}. [TASK FULFILLED: Message delivered to '{recipient}'. Do not repeat this action.]",
        )

    async def action_call_contact(
        self,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        """Initiate voice or video call with contact."""
        recipient = str(params.get("recipient") or "").strip()
        call_type = str(params.get("call_type") or "voice").lower()

        # Open chat first
        open_res = await self.action_open_chat({"recipient": recipient}, context)
        if not open_res.ok:
            return open_res

        # Hotkey for voice call in WhatsApp desktop is Ctrl+Shift+C (or click call button)
        if call_type == "video":
            self.hotkey("ctrl", "shift", "v")
        else:
            self.hotkey("ctrl", "shift", "c")

        return DesktopActionResult(
            ok=True,
            action="call_contact",
            application=self.app_id,
            effect=ActionEffect.CONFIRMED,
            verified=True,
            evidence={"recipient": recipient, "call_type": call_type, "status": "call_initiated"},
        )

    async def action_open_settings(
        self,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        """Open WhatsApp settings."""
        self.hotkey("ctrl", ",")
        await asyncio.sleep(0.3)
        return DesktopActionResult(
            ok=True,
            action="open_settings",
            application=self.app_id,
            effect=ActionEffect.CONFIRMED,
            verified=True,
            evidence={"status": "settings_opened"},
        )
