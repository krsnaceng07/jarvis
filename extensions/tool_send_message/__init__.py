"""tool_send_message — JARVIS cross-platform messenger (Phase 1C)."""

from __future__ import annotations

from jarvis_sdk import PluginApi, define_plugin_entry

from .plugin import SendMessagePlugin


def _register(api: PluginApi) -> None:
    api.register_tool(
        SendMessagePlugin(),
        names=["send_message"],
    )


entry = define_plugin_entry(
    id="tool_send_message",
    kind="tool",
    name="Send Message",
    description="Cross-platform message sender (WhatsApp, Instagram, Telegram, etc.).",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["os:exec", "ui:input-simulation", "network:outbound"],
)
