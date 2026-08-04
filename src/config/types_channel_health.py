"""jarvis.config.types_channel_health — channel heartbeat/health visibility config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.channel-health.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class ChannelHeartbeatVisibilityConfig(TypedDict, total=False):
    """Visibility settings for HEARTBEAT_OK/alert lines in chat."""

    showOk: bool
    showAlerts: bool
    useIndicator: bool


class ChannelHealthMonitorConfig(TypedDict, total=False):
    """Health-monitor restart switch for a channel or account."""

    enabled: bool


__all__ = [
    "ChannelHeartbeatVisibilityConfig",
    "ChannelHealthMonitorConfig",
]
