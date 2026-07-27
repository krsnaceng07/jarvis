"""jarvis.routing.default_account_warnings — shared warning text builders.

OpenClaw parity: mirrors ``src/routing/default-account-warnings.ts``.
Keep paths centralized so doctor/setup messages stay consistent.
"""

from __future__ import annotations

from typing import Any


def _format_channel_default_account_path(channel_key: str) -> str:
    return f"channels.{channel_key}.defaultAccount"


def format_channel_accounts_default_path(channel_key: str) -> str:
    return f"channels.{channel_key}.accounts.default"


def format_set_explicit_default_instruction(channel_key: str) -> str:
    return (
        f"Set {_format_channel_default_account_path(channel_key)} "
        f"or add {format_channel_accounts_default_path(channel_key)}"
    )


def format_set_explicit_default_to_configured_instruction(params: dict[str, Any]) -> str:
    """Variant used when a channel already has configured accounts and should
    point the operator at one of them instead of suggesting a generic default."""
    channel_key = params["channelKey"]
    return (
        f"Set {_format_channel_default_account_path(channel_key)} to one of these accounts, "
        f"or add {format_channel_accounts_default_path(channel_key)}"
    )


__all__ = [
    "format_channel_accounts_default_path",
    "format_set_explicit_default_instruction",
    "format_set_explicit_default_to_configured_instruction",
]
