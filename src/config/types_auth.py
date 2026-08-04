"""jarvis.config.types_auth — auth profile config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.auth.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Auth route selected by a profile.
AuthMode = Literal["api_key", "aws-sdk", "oauth", "token"]


class AuthProfileConfig(TypedDict, total=False):
    provider: str
    mode: str
    email: str
    displayName: str


class AuthCooldownsConfig(TypedDict, total=False):
    """Backoff and rotation policy for auth/profile failures."""

    billingBackoffHours: int
    billingBackoffHoursByProvider: dict
    billingMaxHours: int
    authPermanentBackoffMinutes: int
    authPermanentMaxMinutes: int
    failureWindowHours: int
    overloadedProfileRotations: int
    overloadedBackoffMs: int
    rateLimitedProfileRotations: int


class AuthConfig(TypedDict, total=False):
    profiles: dict
    order: dict
    cooldowns: AuthCooldownsConfig


__all__ = [
    "AuthMode",
    "AuthProfileConfig",
    "AuthCooldownsConfig",
    "AuthConfig",
]
