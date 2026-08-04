"""jarvis.config.zod_schema_allowdeny — allow/deny list Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.allowdeny.ts``.

Focused minimal port: schema factory + small validator helpers.
"""
from __future__ import annotations

from typing import Any


#: Allow/deny action schema.
AllowDenyActionSchema: Any = None  # z.union([z.literal("allow"), z.literal("deny")])


#: Allow/deny chat-type schema (direct | group | channel | deprecated "dm").
AllowDenyChatTypeSchema: Any = None


def create_allow_deny_channel_rules_schema():
    """Build the per-channel allow/deny rules schema.

    Mirrors :func:`createAllowDenyChannelRulesSchema`
    (``shared/config/zod-schema.allowdeny.ts`).
    """
    # Returns a placeholder; the real zod schema lands with the validator.
    return None


def is_allow_deny_action(value: Any) -> bool:
    return value in ("allow", "deny")


def is_allow_deny_chat_type(value: Any) -> bool:
    return value in ("direct", "group", "channel", "dm", None)


__all__ = [
    "AllowDenyActionSchema",
    "AllowDenyChatTypeSchema",
    "create_allow_deny_channel_rules_schema",
    "is_allow_deny_action",
    "is_allow_deny_chat_type",
]
