"""jarvis.config.channel_configured_shared — shared channel-configured checks.

OpenClaw parity: mirrors
``openclaw-main/src/config/channel-configured-shared.ts``.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from .channel_configured import (
    has_meaningful_channel_config_shallow,
    is_statically_channel_configured,
    resolve_channel_config_record,
)


__all__ = [
    "resolve_channel_config_record",
    "has_meaningful_channel_config_shallow",
    "is_statically_channel_configured",
]
