"""jarvis.config.types_channel_messaging_common — common channel messaging config types.

OpenClaw parity: mirrors
``openclaw-main/src/config/types.channel-messaging-common.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class CommonChannelMessagingConfig(TypedDict, total=False):
    name: str
    capabilities: list
    markdown: dict
    configWrites: bool
    enabled: bool
    dmPolicy: str
    allowFrom: list
    defaultTo: str
    groupAllowFrom: list
    groupPolicy: str
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    heartbeat: dict
    healthMonitor: dict
    responsePrefix: str
    mediaMaxMb: int


__all__ = ["CommonChannelMessagingConfig"]
