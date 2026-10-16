"""jarvis.automation.task_flow_types — Task Flow type definitions.

OpenClaw parity: mirrors
``openclaw-main/src/tasks/task-flow-registry.types.ts``

Defines the canonical shared types for the multi-step task flow orchestration
layer that sits above background tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .task_types import JsonValue, TaskNotifyPolicy

# ---------------------------------------------------------------------------
# Discriminants
# ---------------------------------------------------------------------------

TaskFlowSyncMode = Literal["task_mirrored", "managed"]

TaskFlowStatus = Literal[
    "queued",
    "running",
    "waiting",
    "blocked",
    "succeeded",
    "failed",
    "cancelled",
    "lost",
]

# ---------------------------------------------------------------------------
# Validated sets
# ---------------------------------------------------------------------------

TASK_FLOW_SYNC_MODES: frozenset[str] = frozenset(["task_mirrored", "managed"])
TASK_FLOW_STATUSES: frozenset[str] = frozenset(
    ["queued", "running", "waiting", "blocked", "succeeded", "failed", "cancelled", "lost"]
)

# Terminal flow statuses (mirrors isTerminalTaskFlowStatus in OpenClaw)
TASK_FLOW_TERMINAL_STATUSES: frozenset[str] = frozenset(
    ["succeeded", "blocked", "failed", "cancelled", "lost"]
)

# Active (non-terminal) flow statuses
TASK_FLOW_ACTIVE_STATUSES: frozenset[str] = frozenset(["queued", "running", "waiting"])

# Default flow retention (7 days, mirrors TASK_FLOW_RETENTION_MS in maintenance.ts)
TASK_FLOW_RETENTION_MS: int = 7 * 24 * 60 * 60 * 1000

# ---------------------------------------------------------------------------
# Parse helpers (mirrors parsePersistedFlowValue in OpenClaw)
# ---------------------------------------------------------------------------


def _parse_flow_persisted(value: Any, valid: frozenset[str], label: str) -> str:
    if isinstance(value, str) and value in valid:
        return value
    raise ValueError(f"Invalid persisted task flow {label}: {value!r}")


def parse_optional_task_flow_sync_mode(value: Any) -> TaskFlowSyncMode | None:
    if value is None or value == "":
        return None
    return _parse_flow_persisted(value, TASK_FLOW_SYNC_MODES, "sync mode")  # type: ignore[return-value]


def parse_task_flow_status(value: Any) -> TaskFlowStatus:
    return _parse_flow_persisted(value, TASK_FLOW_STATUSES, "status")  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Status predicates
# ---------------------------------------------------------------------------


def is_terminal_flow_status(status: TaskFlowStatus) -> bool:
    """Mirror of OpenClaw ``isTerminalTaskFlowStatus``."""
    return status in TASK_FLOW_TERMINAL_STATUSES


def is_active_flow_status(status: TaskFlowStatus) -> bool:
    return status in TASK_FLOW_ACTIVE_STATUSES


# ---------------------------------------------------------------------------
# Core record type
# ---------------------------------------------------------------------------


@dataclass
class TaskFlowRecord:
    """A persisted multi-step task flow record.

    Mirrors OpenClaw ``TaskFlowRecord``.
    """

    flow_id: str
    sync_mode: TaskFlowSyncMode
    owner_key: str
    revision: int
    status: TaskFlowStatus
    notify_policy: TaskNotifyPolicy
    goal: str
    created_at: float            # ms epoch
    updated_at: float            # ms epoch

    # Optional fields
    requester_origin: dict[str, Any] | None = None
    controller_id: str | None = None   # required for managed flows
    current_step: str | None = None
    blocked_task_id: str | None = None
    blocked_summary: str | None = None
    state_json: JsonValue | None = None
    wait_json: JsonValue | None = None
    cancel_requested_at: float | None = None
    ended_at: float | None = None


# ---------------------------------------------------------------------------
# Update result type (mirrors TaskFlowUpdateResult in OpenClaw)
# ---------------------------------------------------------------------------


@dataclass
class TaskFlowUpdateApplied:
    applied: Literal[True]
    flow: TaskFlowRecord


@dataclass
class TaskFlowUpdateRejected:
    applied: Literal[False]
    reason: Literal["not_found", "revision_conflict", "persist_failed"]
    current: TaskFlowRecord | None = None


TaskFlowUpdateResult = TaskFlowUpdateApplied | TaskFlowUpdateRejected


# ---------------------------------------------------------------------------
# Sync result type (mirrors TaskFlowSyncResult in OpenClaw)
# ---------------------------------------------------------------------------


@dataclass
class TaskFlowSyncOk:
    ok: Literal[True]
    flow: TaskFlowRecord | None


@dataclass
class TaskFlowSyncFailed:
    ok: Literal[False]
    reason: Literal["persist_failed"]
    current: TaskFlowRecord


TaskFlowSyncResult = TaskFlowSyncOk | TaskFlowSyncFailed


__all__ = [
    "TASK_FLOW_ACTIVE_STATUSES",
    "TASK_FLOW_RETENTION_MS",
    "TASK_FLOW_STATUSES",
    "TASK_FLOW_SYNC_MODES",
    "TASK_FLOW_TERMINAL_STATUSES",
    "TaskFlowRecord",
    "TaskFlowStatus",
    "TaskFlowSyncFailed",
    "TaskFlowSyncMode",
    "TaskFlowSyncOk",
    "TaskFlowSyncResult",
    "TaskFlowUpdateApplied",
    "TaskFlowUpdateRejected",
    "TaskFlowUpdateResult",
    "is_active_flow_status",
    "is_terminal_flow_status",
    "parse_optional_task_flow_sync_mode",
    "parse_task_flow_status",
]
