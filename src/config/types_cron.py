"""jarvis.config.types_cron — cron config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.cron.ts``.
"""
from __future__ import annotations

from typing import TypedDict


#: Error types that can trigger retries for one-shot jobs.
CronRetryOn = str  # "rate_limit" | "overloaded" | "network" | "timeout" | "server_error"


class CronRetryConfig(TypedDict, total=False):
    maxAttempts: int
    backoffMs: list
    retryOn: list


class CronFailureAlertConfig(TypedDict, total=False):
    enabled: bool
    after: int
    cooldownMs: int
    includeSkipped: bool
    mode: str
    accountId: str


class CronFailureDestinationConfig(TypedDict, total=False):
    channel: str
    to: str
    accountId: str
    mode: str


class CronConfig(TypedDict, total=False):
    enabled: bool
    store: str
    maxConcurrentRuns: int
    triggers: dict
    retry: CronRetryConfig
    webhook: str
    webhookToken: object  # SecretInput
    sessionRetention: object  # str | false
    failureAlert: CronFailureAlertConfig
    failureDestination: CronFailureDestinationConfig


__all__ = [
    "CronRetryOn",
    "CronRetryConfig",
    "CronFailureAlertConfig",
    "CronFailureDestinationConfig",
    "CronConfig",
]
