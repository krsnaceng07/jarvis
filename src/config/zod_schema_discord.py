"""jarvis.config.zod_schema_discord — shared Discord config schema fragments.

OpenClaw parity: mirrors ``openclaw-main/src/config/zod-schema.discord.ts``.
"""
from __future__ import annotations

import re
from typing import Any


#: Discord ID schema (string or non-negative safe integer, transformed to string).
DiscordIdSchema: Any = None
#: Discord ID list schema.
DiscordIdListSchema: Any = None
#: Discord snowflake (numeric string) schema.
DiscordSnowflakeStringSchema: Any = None
#: Discord DM schema.
DiscordDmSchema: Any = None
#: Discord presence events schema.
DiscordPresenceEventsSchema: Any = None


_DISCORD_ID_NUMERIC_RE = re.compile(r"^\d+$")


def is_valid_discord_snowflake(value: Any) -> bool:
    """Validate a Discord snowflake (numeric ID string)."""
    return isinstance(value, str) and bool(_DISCORD_ID_NUMERIC_RE.match(value))


def is_valid_discord_id(value: Any) -> bool:
    """Validate a Discord ID (string or non-negative safe integer)."""
    if isinstance(value, str):
        return True
    if isinstance(value, int) and value >= 0 and value < (1 << 53):
        return True
    return False


__all__ = [
    "DiscordIdSchema",
    "DiscordIdListSchema",
    "DiscordSnowflakeStringSchema",
    "DiscordDmSchema",
    "DiscordPresenceEventsSchema",
    "is_valid_discord_snowflake",
    "is_valid_discord_id",
]
