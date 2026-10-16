"""jarvis.config.commands_flags — command flag config normalization.

OpenClaw parity: mirrors ``openclaw-main/src/config/commands.flags.ts``.
"""
from __future__ import annotations

from typing import Literal, Union


CommandFlagKey = Literal["restart", "raw"]


def _is_plain_object(value) -> bool:
    return isinstance(value, dict)


def get_own_command_flag_value(
    config: Union[dict, None], key: str
):
    """Get an own command flag value; returns ``None`` if missing or not an own key."""
    if not isinstance(config, dict):
        return None
    commands = config.get("commands")
    if not _is_plain_object(commands) or key not in commands:
        return None
    return commands[key]


def is_command_flag_enabled(
    config: Union[dict, None], key: str
) -> bool:
    """Return true only when a command flag is explicitly enabled.

    Mirrors :func:`isCommandFlagEnabled`
    (``shared/config/commands.flags.ts``).
    """
    return get_own_command_flag_value(config, key) is True


def is_restart_enabled(config: Union[dict, None] = None) -> bool:
    """Return the public restart command state; default on, only disabled by false.

    Mirrors :func:`isRestartEnabled`
    (``shared/config/commands.flags.ts``).
    """
    return get_own_command_flag_value(config, "restart") is not False


__all__ = [
    "CommandFlagKey",
    "get_own_command_flag_value",
    "is_command_flag_enabled",
    "is_restart_enabled",
]
