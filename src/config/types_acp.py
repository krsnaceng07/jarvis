"""jarvis.config.types_acp — ACP session and runtime config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.acp.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class AcpDispatchConfig(TypedDict, total=False):
    enabled: bool


class AcpStreamConfig(TypedDict, total=False):
    coalesceIdleMs: int
    maxChunkChars: int
    repeatSuppression: bool
    deliveryMode: str
    hiddenBoundarySeparator: str
    maxOutputChars: int
    maxSessionUpdateChars: int
    tagVisibility: dict


class AcpRuntimeConfig(TypedDict, total=False):
    ttlMinutes: int
    installCommand: str


class AcpConfig(TypedDict, total=False):
    enabled: bool
    dispatch: AcpDispatchConfig
    backend: str
    fallbacks: list
    defaultAgent: str
    allowedAgents: list
    maxConcurrentSessions: int
    stream: AcpStreamConfig
    runtime: AcpRuntimeConfig


__all__ = [
    "AcpDispatchConfig",
    "AcpStreamConfig",
    "AcpRuntimeConfig",
    "AcpConfig",
]
