"""jarvis.config.types_system_agent — system-agent config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.system-agent.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class SystemAgentRescueConfig(TypedDict, total=False):
    """Remote rescue gate and approval retention policy."""

    enabled: object  # "auto" | bool
    ownerDmOnly: bool
    pendingTtlMinutes: int


class SystemAgentConfig(TypedDict, total=False):
    """Top-level system-agent config block."""

    rescue: SystemAgentRescueConfig


__all__ = [
    "SystemAgentRescueConfig",
    "SystemAgentConfig",
]
