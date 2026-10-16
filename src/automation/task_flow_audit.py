"""jarvis.automation.task_flow_audit — Task Flow audit findings.

OpenClaw parity: mirrors
``openclaw-main/src/tasks/task-flow-registry.audit.ts``

Produces structured audit findings for the task flow registry, covering:
  restore_failed, stale_running, stale_waiting, stale_blocked,
  cancel_stuck, missing_linked_tasks, blocked_task_missing,
  inconsistent_timestamps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Literal

from .task_flow_registry import (
    get_task_flow_registry_restore_failure,
    list_task_flow_records,
)
from .task_flow_types import TaskFlowRecord, is_terminal_flow_status

# ---------------------------------------------------------------------------
# Severity / code taxonomy (mirrors OpenClaw exactly)
# ---------------------------------------------------------------------------

TaskFlowAuditSeverity = Literal["warn", "error"]
TaskFlowAuditCode = Literal[
    "restore_failed",
    "stale_running",
    "stale_waiting",
    "stale_blocked",
    "cancel_stuck",
    "missing_linked_tasks",
    "blocked_task_missing",
    "inconsistent_timestamps",
]

# Default stale thresholds (mirrors OpenClaw defaults)
DEFAULT_FLOW_STALE_RUNNING_MS: int = 30 * 60 * 1000
DEFAULT_FLOW_STALE_WAITING_MS: int = 30 * 60 * 1000
DEFAULT_FLOW_STALE_BLOCKED_MS: int = 30 * 60 * 1000
DEFAULT_FLOW_CANCEL_STUCK_MS: int = 5 * 60 * 1000


@dataclass
class TaskFlowAuditFinding:
    severity: TaskFlowAuditSeverity
    code: TaskFlowAuditCode
    detail: str
    age_ms: float | None = None
    flow: TaskFlowRecord | None = None


@dataclass
class TaskFlowAuditSummary:
    total: int = 0
    warnings: int = 0
    errors: int = 0
    by_code: dict[str, int] = field(default_factory=lambda: {
        "restore_failed": 0,
        "stale_running": 0,
        "stale_waiting": 0,
        "stale_blocked": 0,
        "cancel_stuck": 0,
        "missing_linked_tasks": 0,
        "blocked_task_missing": 0,
        "inconsistent_timestamps": 0,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reference_at(flow: TaskFlowRecord) -> float:
    return flow.updated_at or flow.created_at


def _has_blocking_metadata(flow: TaskFlowRecord) -> bool:
    return bool(
        (flow.blocked_task_id or "").strip()
        or (flow.blocked_summary or "").strip()
        or flow.wait_json is not None
    )


def _find_timestamp_inconsistency(flow: TaskFlowRecord) -> TaskFlowAuditFinding | None:
    if flow.updated_at < flow.created_at:
        return TaskFlowAuditFinding(
            severity="warn", code="inconsistent_timestamps", flow=flow,
            detail="updated_at is earlier than created_at"
        )
    if flow.ended_at is not None and flow.ended_at < flow.created_at:
        return TaskFlowAuditFinding(
            severity="warn", code="inconsistent_timestamps", flow=flow,
            detail="ended_at is earlier than created_at"
        )
    if flow.ended_at is not None and flow.ended_at < flow.updated_at:
        return TaskFlowAuditFinding(
            severity="warn", code="inconsistent_timestamps", flow=flow,
            detail="ended_at is earlier than updated_at"
        )
    return None


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------

def list_task_flow_audit_findings(
    flows: list[TaskFlowRecord] | None = None,
    now_ms: float | None = None,
    stale_running_ms: int = DEFAULT_FLOW_STALE_RUNNING_MS,
    stale_waiting_ms: int = DEFAULT_FLOW_STALE_WAITING_MS,
    stale_blocked_ms: int = DEFAULT_FLOW_STALE_BLOCKED_MS,
    cancel_stuck_ms: int = DEFAULT_FLOW_CANCEL_STUCK_MS,
    # Injected for testing — provides active task ids for a flow
    get_active_task_count_for_flow: Callable[[str], int] | None = None,
    get_blocked_task_exists: Callable[[str], bool] | None = None,
) -> list[TaskFlowAuditFinding]:
    """Mirror of OpenClaw ``listTaskFlowAuditFindings``."""
    if now_ms is None:
        now_ms = time.time() * 1000

    restore_failure = get_task_flow_registry_restore_failure()
    if flows is None:
        flows = [] if restore_failure else list_task_flow_records()

    findings: list[TaskFlowAuditFinding] = []

    # restore_failed — error when registry failed to load from SQLite
    if restore_failure:
        findings.append(TaskFlowAuditFinding(
            severity="error", code="restore_failed",
            detail=f"task-flow registry restore failed: {restore_failure}"
        ))

    for flow in flows:
        ref_at = _reference_at(flow)
        age_ms = max(0.0, now_ms - ref_at)

        # stale_running — error after 30 min still running
        if flow.status == "running" and age_ms >= stale_running_ms:
            findings.append(TaskFlowAuditFinding(
                severity="error", code="stale_running", flow=flow,
                age_ms=age_ms, detail=f"Running flow has not advanced for {age_ms/60000:.1f} min"
            ))

        # stale_waiting — warn after 30 min still waiting
        elif flow.status == "waiting" and age_ms >= stale_waiting_ms:
            findings.append(TaskFlowAuditFinding(
                severity="warn", code="stale_waiting", flow=flow,
                age_ms=age_ms, detail=f"Waiting flow has not advanced for {age_ms/60000:.1f} min"
            ))

        # stale_blocked — warn after 30 min still blocked
        elif flow.status == "blocked" and age_ms >= stale_blocked_ms:
            findings.append(TaskFlowAuditFinding(
                severity="warn", code="stale_blocked", flow=flow,
                age_ms=age_ms, detail=f"Blocked flow has not advanced for {age_ms/60000:.1f} min"
            ))

        # cancel_stuck — warn if cancel requested > 5 min ago, no active child tasks
        if (
            flow.cancel_requested_at is not None
            and not is_terminal_flow_status(flow.status)
        ):
            cancel_age = now_ms - flow.cancel_requested_at
            active_count = (
                get_active_task_count_for_flow(flow.flow_id)
                if get_active_task_count_for_flow is not None
                else 0
            )
            if cancel_age >= cancel_stuck_ms and active_count == 0:
                findings.append(TaskFlowAuditFinding(
                    severity="warn", code="cancel_stuck", flow=flow,
                    age_ms=cancel_age,
                    detail=f"Cancel requested {cancel_age/60000:.1f} min ago, no active tasks, still non-terminal"
                ))

        # missing_linked_tasks — warn/error for stale managed flows with no linked tasks or wait state
        if (
            flow.status in ("running", "waiting", "blocked")
            and flow.sync_mode == "managed"
        ):
            active_count = (
                get_active_task_count_for_flow(flow.flow_id)
                if get_active_task_count_for_flow is not None
                else 0
            )
            if active_count == 0 and not _has_blocking_metadata(flow):
                sev: TaskFlowAuditSeverity = (
                    "error" if flow.status == "running" else "warn"
                )
                findings.append(TaskFlowAuditFinding(
                    severity=sev, code="missing_linked_tasks", flow=flow,
                    age_ms=age_ms,
                    detail=f"Stale {flow.status} managed flow with no linked tasks or wait state"
                ))

        # blocked_task_missing — warn if blocked flow points to nonexistent task
        if flow.status == "blocked" and flow.blocked_task_id:
            exists = (
                get_blocked_task_exists(flow.blocked_task_id)
                if get_blocked_task_exists is not None
                else True  # assume exists when no provider
            )
            if not exists:
                findings.append(TaskFlowAuditFinding(
                    severity="warn", code="blocked_task_missing", flow=flow,
                    age_ms=age_ms,
                    detail=f"Blocked flow points to missing task {flow.blocked_task_id}"
                ))

        # inconsistent_timestamps
        ts_finding = _find_timestamp_inconsistency(flow)
        if ts_finding is not None:
            findings.append(ts_finding)

    # Sort: errors first, then by age_ms desc, then by created_at asc
    findings.sort(key=lambda f: (
        0 if f.severity == "error" else 1,
        -(f.age_ms or 0),
        f.flow.created_at if f.flow else 0,
    ))
    return findings


def build_task_flow_audit_summary(
    findings: list[TaskFlowAuditFinding],
) -> TaskFlowAuditSummary:
    """Build aggregate counts from finding list."""
    s = TaskFlowAuditSummary(total=len(findings))
    for f in findings:
        if f.severity == "error":
            s.errors += 1
        else:
            s.warnings += 1
        s.by_code[f.code] = s.by_code.get(f.code, 0) + 1
    return s


__all__ = [
    "DEFAULT_FLOW_CANCEL_STUCK_MS",
    "DEFAULT_FLOW_STALE_BLOCKED_MS",
    "DEFAULT_FLOW_STALE_RUNNING_MS",
    "DEFAULT_FLOW_STALE_WAITING_MS",
    "TaskFlowAuditCode",
    "TaskFlowAuditFinding",
    "TaskFlowAuditSeverity",
    "TaskFlowAuditSummary",
    "build_task_flow_audit_summary",
    "list_task_flow_audit_findings",
]
