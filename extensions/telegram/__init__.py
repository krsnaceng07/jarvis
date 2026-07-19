"""telegram — JARVIS Telegram channel (Phase 3, simplified).

Mirrors ``extensions/telegram/`` from OpenClaw. Phase 3 ships a
**simplified** port: just enough to send and receive messages, with
a pairing step (the operator sends the first message, the bot
remembers the chat_id).

Full OpenClaw parity (account snapshots, allow-list, inline buttons,
threads, voice, etc.) lands in a later phase. The shapes are
identical, so the extension can grow without breaking compatibility.

Slash command: ``/jarvis <text>`` → forwards to the host's slash
command router (the same one ``jarvis_desktop`` uses for the HUD).
"""
from __future__ import annotations

from jarvis_sdk import PluginApi, define_plugin_entry

from .plugin import TelegramChannel
from .runtime import TelegramState


def _register(api: PluginApi) -> None:
    """Register the Telegram channel surface with the host's PluginApi."""
    state = TelegramState.default()

    # Channel capability (single-active-slot pattern from OpenClaw).
    api.register_channel(
        {
            "id": "telegram",
            "send": TelegramChannel(state).send,
            "listen": TelegramChannel(state).listen,
            "config_schema": {
                "type": "object",
                "properties": {
                    "bot_token": {"type": "string", "description": "Telegram Bot API token."},
                    "polling_interval_sec": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                    },
                },
                "required": ["bot_token"],
            },
        }
    )

    # Doctor contract — flag missing credentials.
    from .doctor import detect_telegram_credentials

    api.register_doctor_contract(
        {
            "id": "telegram.missing_credentials",
            "version": 1,
            "detect_label": "Telegram bot token not configured",
            "detect_path": "~/.jarvis/telegram.json",
            "detect": detect_telegram_credentials,
        }
    )


# ── Plugin entry (mirrors OpenClaw's definePluginEntry) ───────────
entry = define_plugin_entry(
    id="telegram",
    kind="channel",
    name="Telegram",
    description=(
        "Telegram channel: send/receive messages, /jarvis <text> slash "
        "command. Phase 3 simplified port of OpenClaw's telegram."
    ),
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["network:outbound"],
)
