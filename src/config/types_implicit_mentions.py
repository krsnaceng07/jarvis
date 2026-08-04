"""jarvis.config.types_implicit_mentions — channel implicit-mention config types.

OpenClaw parity: mirrors
``openclaw-main/src/config/types.implicit-mentions.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class ChannelImplicitMentionsConfig(TypedDict, total=False):
    """Channel-level implicit-mention toggles."""

    replyToBot: bool
    quotedBot: bool
    threadParticipation: bool


__all__ = ["ChannelImplicitMentionsConfig"]
