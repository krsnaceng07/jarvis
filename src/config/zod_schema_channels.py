"""jarvis.config.zod_schema_channels — channel-related Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.channels.ts``.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ChannelHeartbeatVisibilityConfig(TypedDict, total=False):
    showOk: bool
    showAlerts: bool
    useIndicator: bool


class ChannelHealthMonitorConfig(TypedDict, total=False):
    enabled: bool


#: Channel heartbeat visibility schema.
ChannelHeartbeatVisibilitySchema: Any = None
#: Channel health monitor schema.
ChannelHealthMonitorSchema: Any = None


__all__ = [
    "ChannelHeartbeatVisibilityConfig",
    "ChannelHealthMonitorConfig",
    "ChannelHeartbeatVisibilitySchema",
    "ChannelHealthMonitorSchema",
]
