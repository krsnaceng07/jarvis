"""jarvis.config.zod_schema_implicit_mentions — implicit-mention Zod schema fragment.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.implicit-mentions.ts``.
"""
from __future__ import annotations

from typing import Any


#: Channel implicit-mention schema.
ChannelImplicitMentionsSchema: Any = None  # z.object({...}).strict()


def is_valid_implicit_mentions(value: Any) -> bool:
    """Validate a channel implicit-mentions value."""
    if not isinstance(value, dict):
        return False
    return set(value.keys()) <= {"replyToBot", "quotedBot", "threadParticipation"}


__all__ = [
    "ChannelImplicitMentionsSchema",
    "is_valid_implicit_mentions",
]
