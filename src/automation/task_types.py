"""jarvis.automation.task_types — Background task ledger type definitions.

OpenClaw parity: mirrors
``openclaw-main/src/tasks/task-registry.types.ts``

Defines the canonical shared types for all background task tracking:
ACP runs, subagent spawns, automation job runs, and CLI-initiated operations.
These are RECORDS not schedulers — automations decide WHEN, tasks track WHAT.
"""

from __future__ import annotations

from typing import Any, Literal

# ---------------------------------------------------------------------------
# Primitive discriminants
# ---------------------------------------------------------------------------

TaskRuntime = Literal["subagent", "acp", "cli", "cron"]

TaskStatus = Literal[
    "queued", "running", "succeeded", "failed", "timed_out", "cancelled", "lost"
]

TaskDeliveryStatus = Literal[
    "pending", "delivered", "session_queued", "failed", "parent_missing", "not_applicable"
]

TaskNotifyPolicy = Literal["done_only", "state_changes", "silent"]

# Semantic success detail for required-completion task outcomes.
TaskTerminalOutcome = Literal["succeeded", "blocked"]

TaskScopeKind = Literal["session", "system"]

TaskEventKind = Literal[
    "queued", "running", "succeeded", "failed", "timed_out", "cancelled", "lost", "progress"
]

# ---------------------------------------------------------------------------
# Validated sets (mirrors OpenClaw's Set<T> constants)
# ---------------------------------------------------------------------------

TASK_RUNTIMES: frozenset[str] = frozenset(["subagent", "acp", "cli", "cron"])
TASK_STATUSES: frozenset[str] = frozenset(
    ["queued", "running", "succeeded", "failed", "timed_out", "cancelled", "lost"]
)
TASK_DELIVERY_STATUSES: frozenset[str] = frozenset(
    ["pending", "delivered", "session_queued", "failed", "parent_missing", "not_applicable"]
)
TASK_NOTIFY_POLICIES: frozenset[str] = frozenset(["done_only", "state_changes", "silent"])
TASK_TERMINAL_OUTCOMES: frozenset[str] = frozenset(["succeeded", "blocked"])
TASK_SCOPE_KINDS: frozenset[str] = frozenset(["session", "system"])

# Active (non-terminal) task statuses
TASK_ACTIVE_STATUSES: frozenset[str] = frozenset(["queued", "running"])

# Failure statuses (mirrors isFailureTask check in OpenClaw)
TASK_FAILURE_STATUSES: frozenset[str] = frozenset(["failed", "timed_out", "lost"])

# Default notify policy per runtime (mirrors OpenClaw docs table)
DEFAULT_NOTIFY_POLICY_BY_RUNTIME: dict[str, str] = {
    "acp": "done_only",
    "subagent": "done_only",
    "cron": "silent",
    "cli": "silent",
}

# ---------------------------------------------------------------------------
# Parse helpers (mirrors parsePersistedTaskValue generic in OpenClaw)
# ---------------------------------------------------------------------------

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def _parse_persisted(value: Any, valid: frozenset[str], label: str) -> str:
    if isinstance(value, str) and value in valid:
        return value
    raise ValueError(f"Invalid persisted task {label}: {value!r}")


def parse_task_runtime(value: Any) -> TaskRuntime:
    return _parse_persisted(value, TASK_RUNTIMES, "runtime")  # type: ignore[return-value]


def parse_task_status(value: Any) -> TaskStatus:
    return _parse_persisted(value, TASK_STATUSES, "status")  # type: ignore[return-value]


def parse_task_delivery_status(value: Any) -> TaskDeliveryStatus:
    return _parse_persisted(value, TASK_DELIVERY_STATUSES, "delivery status")  # type: ignore[return-value]


def parse_task_notify_policy(value: Any) -> TaskNotifyPolicy:
    return _parse_persisted(value, TASK_NOTIFY_POLICIES, "notify policy")  # type: ignore[return-value]


def parse_task_scope_kind(value: Any) -> TaskScopeKind:
    return _parse_persisted(value, TASK_SCOPE_KINDS, "scope kind")  # type: ignore[return-value]


def parse_optional_task_terminal_outcome(value: Any) -> TaskTerminalOutcome | None:
    if value is None or value == "":
        return None
    return _parse_persisted(value, TASK_TERMINAL_OUTCOMES, "terminal outcome")  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Status helpers (mirrors task-executor-policy.ts / task-status.ts)
# ---------------------------------------------------------------------------

def is_terminal_task_status(status: TaskStatus) -> bool:
    """Mirror of OpenClaw ``isTerminalTaskStatus``."""
    return status not in TASK_ACTIVE_STATUSES


def is_active_task_status(status: TaskStatus) -> bool:
    return status in TASK_ACTIVE_STATUSES


def is_failure_task_status(status: TaskStatus) -> bool:
    """Mirror of OpenClaw ``isFailureTask``."""
    return status in TASK_FAILURE_STATUSES


# ---------------------------------------------------------------------------
# Core record types
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class TaskEventRecord:
    at: float  # ms epoch
    kind: TaskEventKind
    summary: str | None = None


@dataclass
class TaskDeliveryState:
    task_id: str
    requester_origin: dict[str, Any] | None = None
    last_notified_event_at: float | None = None


@dataclass
class TaskRecord:
    """A persisted background task record. Mirrors OpenClaw ``TaskRecord``."""

    task_id: str
    runtime: TaskRuntime
    requester_session_key: str
    owner_key: str
    scope_kind: TaskScopeKind
    task: str                          # human-readable title
    status: TaskStatus
    delivery_status: TaskDeliveryStatus
    notify_policy: TaskNotifyPolicy
    created_at: float                  # ms epoch

    # Optional identity
    task_kind: str | None = None       # e.g. "image_generation"
    source_id: str | None = None       # e.g. cron job id
    child_session_key: str | None = None
    parent_flow_id: str | None = None
    parent_task_id: str | None = None
    agent_id: str | None = None
    requester_agent_id: str | None = None
    run_id: str | None = None
    label: str | None = None

    # Lifecycle timestamps (ms epochs)
    started_at: float | None = None
    ended_at: float | None = None
    last_event_at: float | None = None
    cleanup_after: float | None = None

    # Progress/result
    tool_use_count: int | None = None
    last_tool_name: str | None = None
    error: str | None = None
    progress_summary: str | None = None
    terminal_summary: str | None = None
    terminal_outcome: TaskTerminalOutcome | None = None
    detail: JsonValue | None = None


# ---------------------------------------------------------------------------
# Aggregate summary types (mirrors task-registry.summary.ts)
# ---------------------------------------------------------------------------

@dataclass
class TaskStatusCounts:
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    timed_out: int = 0
    cancelled: int = 0
    lost: int = 0


@dataclass
class TaskRuntimeCounts:
    subagent: int = 0
    acp: int = 0
    cli: int = 0
    cron: int = 0


@dataclass
class TaskRegistrySummary:
    total: int = 0
    active: int = 0
    terminal: int = 0
    failures: int = 0
    by_status: TaskStatusCounts = field(default_factory=TaskStatusCounts)
    by_runtime: TaskRuntimeCounts = field(default_factory=TaskRuntimeCounts)


__all__ = [
    "DEFAULT_NOTIFY_POLICY_BY_RUNTIME",
    "TASK_ACTIVE_STATUSES",
    "TASK_DELIVERY_STATUSES",
    "TASK_FAILURE_STATUSES",
    "TASK_NOTIFY_POLICIES",
    "TASK_RUNTIMES",
    "TASK_SCOPE_KINDS",
    "TASK_STATUSES",
    "TASK_TERMINAL_OUTCOMES",
    "JsonValue",
    "TaskDeliveryState",
    "TaskDeliveryStatus",
    "TaskEventKind",
    "TaskEventRecord",
    "TaskNotifyPolicy",
    "TaskRecord",
    "TaskRegistrySummary",
    "TaskRuntime",
    "TaskRuntimeCounts",
    "TaskScopeKind",
    "TaskStatus",
    "TaskStatusCounts",
    "TaskTerminalOutcome",
    "is_active_task_status",
    "is_failure_task_status",
    "is_terminal_task_status",
    "parse_optional_task_terminal_outcome",
    "parse_task_delivery_status",
    "parse_task_notify_policy",
    "parse_task_runtime",
    "parse_task_scope_kind",
    "parse_task_status",
]
