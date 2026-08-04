"""jarvis.config.types_cloud_workers — cloud worker profile config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.cloud-workers.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Worker install method.
CloudWorkerInstall = Literal["bundle", "npm"]


class CloudWorkerLifetimePolicyConfig(TypedDict, total=False):
    """Lifecycle policy for a cloud-worker environment."""

    idleTimeoutMinutes: int
    maxLifetimeMinutes: int


class CloudWorkerProfileConfig(TypedDict, total=False):
    provider: str
    install: str
    settings: dict
    lifetime: CloudWorkerLifetimePolicyConfig


class CloudWorkersConfig(TypedDict, total=False):
    profiles: dict


__all__ = [
    "CloudWorkerInstall",
    "CloudWorkerLifetimePolicyConfig",
    "CloudWorkerProfileConfig",
    "CloudWorkersConfig",
]
