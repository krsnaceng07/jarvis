"""jarvis.desktop_automation.tools.whatsapp_tools — Granular WhatsApp automation tools.

OpenClaw parity: Granular, schema-validated tools replacing monolithic
untyped tool calls and preventing model guessing.
"""

from __future__ import annotations

from typing import Any, Dict

from ..providers.registry import ProviderRegistry


def _get_whatsapp_provider():
    registry = ProviderRegistry.get_instance()
    provider = registry.get_provider("whatsapp")
    if not provider:
        from ..providers.whatsapp_provider import WhatsAppDesktopProvider
        provider = WhatsAppDesktopProvider()
        registry.register_provider(provider)
    return provider


async def whatsapp_get_state_tool(args: Dict[str, Any]) -> str:
    """Check whether WhatsApp is running, minimized, in the foreground, and the active chat."""
    provider = _get_whatsapp_provider()
    state = await provider.get_state()
    return (
        f"WhatsApp State: Running={state.is_running}, Minimized={state.is_minimized}, "
        f"Foreground={state.is_foreground}, Active Chat='{state.active_chat}', "
        f"Window Title='{state.window_title}'"
    )


async def whatsapp_open_tool(args: Dict[str, Any]) -> str:
    """Open or restore WhatsApp and bring it to the active foreground."""
    provider = _get_whatsapp_provider()
    focused = await provider.ensure_active()
    if focused:
        return "WhatsApp was successfully restored and brought to the active foreground."
    return "Failed to bring WhatsApp to the foreground. Please ensure WhatsApp is installed."


async def whatsapp_search_contact_tool(args: Dict[str, Any]) -> str:
    """Search for a contact or group on WhatsApp."""
    query = str(args.get("query") or args.get("contact") or "").strip()
    if not query:
        return "Error: 'query' or 'contact' parameter is required for contact search."
    provider = _get_whatsapp_provider()
    candidates = await provider.search_contacts(query)
    if not candidates:
        return f"No contacts found matching '{query}'."
    names = ", ".join(f"'{c.name}'" for c in candidates)
    return f"Found matching contacts: {names}."


async def whatsapp_open_chat_tool(args: Dict[str, Any]) -> str:
    """Open a specific chat on WhatsApp and verify the chat header."""
    recipient = str(args.get("recipient") or args.get("contact") or "").strip()
    if not recipient:
        return "Error: 'recipient' parameter is required to open a chat."
    provider = _get_whatsapp_provider()
    res = await provider.open_chat(recipient)
    if res.ok:
        return res.output_text or f"Chat with '{recipient}' opened successfully."
    return f"Failed to open chat with '{recipient}': {res.error}"


async def whatsapp_send_message_tool(args: Dict[str, Any]) -> str:
    """Send an exact message to a WhatsApp recipient with foreground verification."""
    recipient = str(args.get("recipient") or args.get("target") or "").strip()
    message = str(args.get("message") or args.get("text") or "").strip()
    if not recipient:
        return "Error: 'recipient' parameter is required to send a message."
    if not message:
        return "Error: 'message' text cannot be empty."

    provider = _get_whatsapp_provider()
    res = await provider.send_message(recipient, message)
    if res.ok:
        return res.output_text or f"Message sent to '{recipient}'."
    return f"Failed to send message to '{recipient}': {res.error}"


async def whatsapp_verify_message_tool(args: Dict[str, Any]) -> str:
    """Verify that a message to a recipient was delivered and recorded in the active chat."""
    recipient = str(args.get("recipient") or "").strip()
    message = str(args.get("message") or "").strip()
    provider = _get_whatsapp_provider()
    verified = await provider.verify_delivery(recipient, message)
    if verified:
        return f"Verified: Chat with '{recipient}' is active and message delivery confirmed."
    return f"Could not verify message delivery to '{recipient}'."


WHATSAPP_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "whatsapp_get_state",
            "description": "Inspect WhatsApp application state (running, minimized, foreground, active chat).",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whatsapp_open",
            "description": "Restore, unminimize, and bring WhatsApp Desktop to the active foreground.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whatsapp_search_contact",
            "description": "Search for a contact or group on WhatsApp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The contact name or phone number to search for."}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whatsapp_open_chat",
            "description": "Open a WhatsApp conversation with a recipient and assert active header.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "The recipient or contact name to open chat with."}
                },
                "required": ["recipient"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whatsapp_send_message",
            "description": "Send a WhatsApp message to a recipient. Verifies WhatsApp is in foreground, restores from minimized, and verifies delivery.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Name of the person or group to send the message to."},
                    "message": {"type": "string", "description": "Exact text message to send."}
                },
                "required": ["recipient", "message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whatsapp_verify_message",
            "description": "Verify that a message to a recipient was delivered.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Recipient name."}
                },
                "required": ["recipient"],
                "additionalProperties": False,
            },
        },
    },
]
