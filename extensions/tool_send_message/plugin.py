"""SendMessagePlugin — JARVIS cross-platform messenger.

Migrated from ``actions/send_message.py``. Same dispatch table, same
pyautogui sequences. Returns ``Result[str]`` (Phase 1C contract).
"""
from __future__ import annotations

from typing import Any

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)

from . import runtime


SEND_MESSAGE_TOOL = ToolDecl(
    name="send_message",
    description=(
        "Sends a message to a contact via WhatsApp, Instagram, Telegram, "
        "or any other app that supports Ctrl+F search. Uses visual "
        "automation (pyautogui)."
    ),
    parameters=[
        ToolParam(
            name="receiver",
            type="string",
            description="Contact name to send to.",
            required=True,
        ),
        ToolParam(
            name="message_text",
            type="string",
            description="The message content.",
            required=True,
        ),
        ToolParam(
            name="platform",
            type="string",
            description=(
                "whatsapp | instagram | telegram | <any app name>. "
                "Default: whatsapp."
            ),
            required=False,
        ),
    ],
    returns="string",
    category="communication",
)


def _route_platform(platform: str) -> tuple[str, str]:
    """Normalize the platform string to a known sender key.

    Returns ``(sender_key, original_platform)``. The sender key is one
    of ``"whatsapp"``, ``"instagram"``, ``"telegram"``, or
    ``"generic"``. The original is preserved for the user-facing
    message.
    """
    p = platform.lower().strip()
    if "whatsapp" in p or p in ("wp", "wapp"):
        return "whatsapp", platform
    if "instagram" in p or p in ("ig", "insta"):
        return "instagram", platform
    if "telegram" in p or p == "tg":
        return "telegram", platform
    return "generic", platform


class SendMessagePlugin(ToolPlugin):
    """Universal messenger. Stateless."""

    id = "tool_send_message"
    kind = "tool"
    version = "0.1.0"
    description = "Cross-platform message sender (WhatsApp, Instagram, Telegram, etc.)."

    def init(self, ctx: Any) -> None:
        return

    async def shutdown(self) -> None:
        return None

    @property
    def tools(self) -> list[ToolDecl]:
        return [SEND_MESSAGE_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        if name != "send_message":
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        return self._send(args)

    def _send(self, args: dict[str, Any]) -> Result[str]:
        receiver = (args.get("receiver") or "").strip()
        message_text = (args.get("message_text") or "").strip()
        platform = (args.get("platform") or "whatsapp").strip().lower()

        if not receiver:
            return Err("Please specify who to send the message to, sir.", code="MISSING_ARG")
        if not message_text:
            return Err("Please specify what message to send, sir.", code="MISSING_ARG")

        key, original = _route_platform(platform)
        print(f"[SendMessage] {original} → {receiver}: {message_text[:40]}")
        if key == "whatsapp":
            return Ok(runtime.send_whatsapp(receiver, message_text))
        if key == "instagram":
            return Ok(runtime.send_instagram(receiver, message_text))
        if key == "telegram":
            return Ok(runtime.send_telegram(receiver, message_text))
        return Ok(runtime.send_generic(original, receiver, message_text))


__all__ = ["SEND_MESSAGE_TOOL", "SendMessagePlugin"]
