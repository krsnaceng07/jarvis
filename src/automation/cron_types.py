"""jarvis.automation.cron_types — Cron/Automations type definitions.

OpenClaw parity: mirrors
``openclaw-main/src/cron/types.ts``
``openclaw-main/src/config/types.cron.ts``
``openclaw-main/src/config/cron-limits.ts``
``openclaw-main/src/cron/types-shared.ts``

These are the canonical shared types for the Jarvis automation scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Schedule kinds
# ---------------------------------------------------------------------------

CronScheduleKind = Literal["at", "every", "cron", "on-exit", "stream"]

# ---------------------------------------------------------------------------
# Payload kinds
# ---------------------------------------------------------------------------

CronPayloadKind = Literal["systemEvent", "agentTurn", "command", "script", "heartbeat"]

# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

CronDeliveryMode = Literal["none", "announce", "webhook"]
CronRunStatus = Literal["ok", "error", "skipped"]
CronDeliveryStatus = Literal["delivered", "not-delivered", "error"]

# ---------------------------------------------------------------------------
# Session targets
# ---------------------------------------------------------------------------

# Allowed session target forms:
#   "main"              — default agent main session lane
#   "isolated"          — fresh isolated session per run
#   "current"           — bound to conversation at creation time
#   "session:<id>"      — persistent named session
CronSessionTarget = str  # validated via session_target.py helpers

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

CronRetryOn = Literal["rate_limit", "overloaded", "network", "timeout", "server_error"]


@dataclass(frozen=True, slots=True)
class CronRetryConfig:
    """Per-job retry policy for transient execution errors (one-shot jobs)."""

    max_attempts: int = 3
    backoff_ms: tuple[int, ...] = (30_000, 60_000, 300_000)
    retry_on: tuple[CronRetryOn, ...] | None = None  # None → retry all transient types


# ---------------------------------------------------------------------------
# Failure alerts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronFailureAlertConfig:
    enabled: bool = False
    after: int = 1  # number of consecutive failures before alerting
    cooldown_ms: int = 0
    include_skipped: bool = False
    mode: Literal["announce", "webhook"] = "announce"
    account_id: str | None = None


@dataclass(frozen=True, slots=True)
class CronFailureDestination:
    channel: str | None = None
    to: str | None = None
    account_id: str | None = None
    mode: Literal["announce", "webhook"] | None = None


# ---------------------------------------------------------------------------
# Delivery config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronCompletionDestination:
    """Webhook completion destination used alongside chat delivery."""

    mode: Literal["webhook"]
    to: str | None = None


@dataclass(frozen=True, slots=True)
class CronDelivery:
    mode: CronDeliveryMode = "none"
    channel: str | None = None
    to: str | None = None
    thread_id: str | int | None = None
    account_id: str | None = None
    best_effort: bool = False
    completion_destination: CronCompletionDestination | None = None
    failure_destination: CronFailureDestination | None = None


# ---------------------------------------------------------------------------
# Schedule shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronScheduleAt:
    kind: Literal["at"]
    at: str  # ISO 8601 or relative like "20m"


@dataclass(frozen=True, slots=True)
class CronScheduleEvery:
    kind: Literal["every"]
    every_ms: int
    anchor_ms: int | None = None


@dataclass(frozen=True, slots=True)
class CronScheduleCron:
    kind: Literal["cron"]
    expr: str
    tz: str | None = None
    stagger_ms: int | None = None  # explicit stagger window; None = auto


@dataclass(frozen=True, slots=True)
class CronScheduleOnExit:
    kind: Literal["on-exit"]
    command: str  # argv command to watch
    cwd: str | None = None


@dataclass(frozen=True, slots=True)
class CronScheduleStream:
    kind: Literal["stream"]
    command: list[str]  # exact argv
    mode: Literal["line", "match"] = "line"
    match_pattern: str | None = None
    batch_ms: int = 250
    max_batch_bytes: int = 16_384


CronSchedule = (
    CronScheduleAt | CronScheduleEvery | CronScheduleCron | CronScheduleOnExit | CronScheduleStream
)

# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronPacing:
    """Dynamic cadence bounds for recurring jobs."""

    min: str | None = None  # e.g. "15m"
    max: str | None = None  # e.g. "4h"


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronPayloadSystemEvent:
    kind: Literal["systemEvent"]
    text: str
    wake_mode: Literal["now", "next-heartbeat"] | None = None


@dataclass(frozen=True, slots=True)
class CronPayloadAgentTurn:
    kind: Literal["agentTurn"]
    message: str
    model: str | None = None
    thinking: str | None = None
    light_context: bool = False
    tools: list[str] | None = None  # None = unrestricted
    fallbacks: list[str] | None = None


@dataclass(frozen=True, slots=True)
class CronPayloadCommand:
    kind: Literal["command"]
    argv: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 600
    output_max_bytes: int = 0  # 0 = unlimited


@dataclass(frozen=True, slots=True)
class CronPayloadScript:
    kind: Literal["script"]
    source: str  # JS source (ported: Python callable string or path)
    timeout_seconds: int = 300
    tool_budget: int = 50


@dataclass(frozen=True, slots=True)
class CronPayloadHeartbeat:
    """System-owned heartbeat payload; cannot be created via CLI/API."""

    kind: Literal["heartbeat"]


CronPayload = (
    CronPayloadSystemEvent
    | CronPayloadAgentTurn
    | CronPayloadCommand
    | CronPayloadScript
    | CronPayloadHeartbeat
)

# ---------------------------------------------------------------------------
# Trigger (condition watcher)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronTrigger:
    """Event-trigger condition script for every/cron/stream schedules."""

    script: str  # condition script source
    once: bool = False  # disable job after first successful fired payload


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


@dataclass
class CronJob:
    """A persisted automation job record."""

    job_id: str
    name: str
    schedule: CronSchedule
    payload: CronPayload
    session_target: str = "isolated"
    agent_id: str | None = None
    delivery: CronDelivery = field(default_factory=CronDelivery)
    enabled: bool = True
    pacing: CronPacing | None = None
    trigger: CronTrigger | None = None
    retry: CronRetryConfig = field(default_factory=CronRetryConfig)
    failure_alert: CronFailureAlertConfig = field(default_factory=CronFailureAlertConfig)
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_run_status: CronRunStatus | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0
    declaration_key: str | None = None  # stable key for idempotent creates
    delete_after_run: bool = False
    state: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------


@dataclass
class CronRunRecord:
    """Terminal result record for one automation execution."""

    run_id: str
    job_id: str
    status: CronRunStatus
    started_at_ms: int
    finished_at_ms: int
    summary: str | None = None
    error: str | None = None
    delivery_status: CronDeliveryStatus | None = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CronConfig:
    enabled: bool = True
    max_concurrent_runs: int = 8
    triggers_enabled: bool = False
    trigger_min_interval_ms: int = 30_000
    webhook_token: str | None = None
    session_retention: str | Literal[False] = "24h"
    failure_alert: CronFailureAlertConfig = field(default_factory=CronFailureAlertConfig)


# History retention cap (mirrors CRON_HISTORY_KEEP_PER_JOB in OpenClaw)
CRON_HISTORY_KEEP_PER_JOB = 2_000

# Default concurrency (mirrors DEFAULT_CRON_MAX_CONCURRENT_RUNS in OpenClaw)
DEFAULT_CRON_MAX_CONCURRENT_RUNS = 8

# Trigger minimum interval (mirrors DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS in OpenClaw)
DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS = 30_000


def resolve_cron_max_concurrent_runs(config: CronConfig | None) -> int:
    """Mirror of OpenClaw ``resolveCronMaxConcurrentRuns``."""
    if config is None:
        return DEFAULT_CRON_MAX_CONCURRENT_RUNS
    raw = config.max_concurrent_runs
    if isinstance(raw, (int, float)) and raw == raw:  # finite check
        return max(1, int(raw))
    return DEFAULT_CRON_MAX_CONCURRENT_RUNS


def resolve_cron_trigger_min_interval_ms(config: CronConfig | None) -> int:
    """Mirror of OpenClaw ``resolveCronTriggerMinIntervalMs``."""
    if config is None:
        return DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS
    raw = config.trigger_min_interval_ms
    if isinstance(raw, (int, float)) and raw == raw:
        return max(1, int(raw))
    return DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS


__all__ = [
    "CRON_HISTORY_KEEP_PER_JOB",
    "DEFAULT_CRON_MAX_CONCURRENT_RUNS",
    "DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS",
    "CronCompletionDestination",
    "CronConfig",
    "CronDelivery",
    "CronDeliveryMode",
    "CronDeliveryStatus",
    "CronFailureAlertConfig",
    "CronFailureDestination",
    "CronJob",
    "CronPacing",
    "CronPayload",
    "CronPayloadAgentTurn",
    "CronPayloadCommand",
    "CronPayloadHeartbeat",
    "CronPayloadKind",
    "CronPayloadScript",
    "CronPayloadSystemEvent",
    "CronRetryConfig",
    "CronRetryOn",
    "CronRunRecord",
    "CronRunStatus",
    "CronSchedule",
    "CronScheduleAt",
    "CronScheduleCron",
    "CronScheduleEvery",
    "CronScheduleKind",
    "CronScheduleOnExit",
    "CronScheduleStream",
    "CronSessionTarget",
    "CronTrigger",
    "resolve_cron_max_concurrent_runs",
    "resolve_cron_trigger_min_interval_ms",
]
