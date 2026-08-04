"""jarvis.config.types_queue — inbound queue handling config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.queue.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Queue handling mode for inbound channel messages.
QueueMode = Literal["steer", "followup", "collect", "interrupt"]
#: Queue drop policy when a queue is full.
QueueDropPolicy = Literal["old", "new", "summarize"]


class QueueModeByProvider(TypedDict, total=False):
    whatsapp: str
    telegram: str
    discord: str
    irc: str
    googlechat: str
    slack: str
    mattermost: str
    signal: str
    imessage: str
    msteams: str
    webchat: str
    matrix: str


__all__ = [
    "QueueMode",
    "QueueDropPolicy",
    "QueueModeByProvider",
]
