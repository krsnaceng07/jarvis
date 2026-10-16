"""jarvis.automation.task_registry — In-process task ledger.

OpenClaw parity: mirrors
``openclaw-main/src/tasks/task-registry.process-state.ts``
``openclaw-main/src/tasks/task-registry-records.ts``
``openclaw-main/src/tasks/task-registry.summary.ts``
``openclaw-main/src/tasks/task-registry.audit.shared.ts``
``openclaw-main/src/tasks/task-registry.audit.ts``

Single in-process registry: Map-backed indexes for O(1) lookup by taskId,
runId, ownerKey, parentFlowId, and related session key.
Audit findings match OpenClaw severity/code taxonomy exactly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .task_retention import (
    STALE_QUEUED_MS,
    STALE_RUNNING_MS,
    is_expired_task,
    is_recent_terminal_task,
    resolve_effective_task_cleanup_after,
    resolve_task_cleanup_after,
)
from .task_types import (
    TaskDeliveryState,
    TaskRecord,
    TaskRegistrySummary,
    is_active_task_status,
    is_failure_task_status,
    is_terminal_task_status,
)

# ---------------------------------------------------------------------------
# Process-local state (mirrors TaskRegistryProcessState in OpenClaw)
# ---------------------------------------------------------------------------

class _TaskRegistryState:
    """Singleton in-process state backing all task lookups."""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}
        self.delivery_states: dict[str, TaskDeliveryState] = {}
        # Indexes
        self.ids_by_run_id: dict[str, set[str]] = {}
        self.ids_by_owner_key: dict[str, set[str]] = {}
        self.ids_by_parent_flow_id: dict[str, set[str]] = {}
        self.ids_by_session_key: dict[str, set[str]] = {}  # requester + child
        self.pending_delivery_ids: set[str] = set()


_REGISTRY = _TaskRegistryState()


def _get_registry() -> _TaskRegistryState:
    return _REGISTRY


def _reset_registry_for_testing() -> None:
    """Test helper: clear all in-process state."""
    global _REGISTRY
    _REGISTRY = _TaskRegistryState()


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _index_add(index: dict[str, set[str]], key: str, task_id: str) -> None:
    if key not in index:
        index[key] = set()
    index[key].add(task_id)


def _index_remove(index: dict[str, set[str]], key: str, task_id: str) -> None:
    s = index.get(key)
    if s:
        s.discard(task_id)
        if not s:
            del index[key]


def _add_task_to_indexes(r: _TaskRegistryState, task: TaskRecord) -> None:
    tid = task.task_id
    if task.run_id:
        _index_add(r.ids_by_run_id, task.run_id, tid)
    _index_add(r.ids_by_owner_key, task.owner_key, tid)
    if task.parent_flow_id:
        _index_add(r.ids_by_parent_flow_id, task.parent_flow_id, tid)
    _index_add(r.ids_by_session_key, task.requester_session_key, tid)
    if task.child_session_key:
        _index_add(r.ids_by_session_key, task.child_session_key, tid)


def _remove_task_from_indexes(r: _TaskRegistryState, task: TaskRecord) -> None:
    tid = task.task_id
    if task.run_id:
        _index_remove(r.ids_by_run_id, task.run_id, tid)
    _index_remove(r.ids_by_owner_key, task.owner_key, tid)
    if task.parent_flow_id:
        _index_remove(r.ids_by_parent_flow_id, task.parent_flow_id, tid)
    _index_remove(r.ids_by_session_key, task.requester_session_key, tid)
    if task.child_session_key:
        _index_remove(r.ids_by_session_key, task.child_session_key, tid)


# ---------------------------------------------------------------------------
# Record normalization (mirrors task-registry-records.ts)
# ---------------------------------------------------------------------------

def normalize_task_timestamps(task: TaskRecord) -> TaskRecord:
    """Mirror of OpenClaw ``normalizeTaskTimestamps``.

    Detached runtimes can report lifecycle times captured before registry
    insertion; keep createdAt as the visible lifecycle floor.
    """
    created_at = task.created_at
    for candidate in (task.started_at, task.last_event_at, task.ended_at):
        if candidate is not None and candidate < created_at:
            created_at = candidate

    started_at = max(task.started_at, created_at) if task.started_at is not None else None
    floor = started_at if started_at is not None else created_at
    last_event_at = max(task.last_event_at, floor) if task.last_event_at is not None else None
    ended_at = max(task.ended_at, floor) if task.ended_at is not None else None

    # Return same object when nothing changed
    if (
        created_at == task.created_at
        and started_at == task.started_at
        and last_event_at == task.last_event_at
        and ended_at == task.ended_at
    ):
        return task

    from dataclasses import replace
    return replace(
        task,
        created_at=created_at,
        started_at=started_at,
        last_event_at=last_event_at,
        ended_at=ended_at,
    )


# ---------------------------------------------------------------------------
# CRUD — registry mutations
# ---------------------------------------------------------------------------

def upsert_task(task: TaskRecord) -> None:
    """Insert or replace a task record and update all indexes."""
    r = _get_registry()
    task = normalize_task_timestamps(task)
    existing = r.tasks.get(task.task_id)
    if existing is not None:
        _remove_task_from_indexes(r, existing)
    r.tasks[task.task_id] = task
    _add_task_to_indexes(r, task)
    if task.delivery_status == "pending":
        r.pending_delivery_ids.add(task.task_id)
    else:
        r.pending_delivery_ids.discard(task.task_id)


def remove_task(task_id: str) -> bool:
    """Remove a task record. Returns True if it existed."""
    r = _get_registry()
    task = r.tasks.pop(task_id, None)
    if task is None:
        return False
    _remove_task_from_indexes(r, task)
    r.pending_delivery_ids.discard(task_id)
    r.delivery_states.pop(task_id, None)
    return True


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def get_task_by_id(task_id: str) -> TaskRecord | None:
    return _get_registry().tasks.get(task_id)


def find_task_by_run_id(run_id: str) -> TaskRecord | None:
    r = _get_registry()
    ids = r.ids_by_run_id.get(run_id, set())
    for tid in ids:
        task = r.tasks.get(tid)
        if task is not None:
            return task
    return None


def list_task_records() -> list[TaskRecord]:
    """Return all tasks sorted newest-first (by createdAt)."""
    r = _get_registry()
    return sorted(r.tasks.values(), key=lambda t: -t.created_at)


def list_tasks_for_session_key(session_key: str) -> list[TaskRecord]:
    r = _get_registry()
    ids = r.ids_by_session_key.get(session_key, set())
    return [r.tasks[tid] for tid in ids if tid in r.tasks]


def list_tasks_for_owner_key(owner_key: str) -> list[TaskRecord]:
    r = _get_registry()
    ids = r.ids_by_owner_key.get(owner_key, set())
    return [r.tasks[tid] for tid in ids if tid in r.tasks]


def list_tasks_for_flow(flow_id: str) -> list[TaskRecord]:
    r = _get_registry()
    ids = r.ids_by_parent_flow_id.get(flow_id, set())
    return [r.tasks[tid] for tid in ids if tid in r.tasks]


# ---------------------------------------------------------------------------
# Summary (mirrors task-registry.summary.ts)
# ---------------------------------------------------------------------------

def summarize_task_records(records: Iterable[TaskRecord]) -> TaskRegistrySummary:
    """Mirror of OpenClaw ``summarizeTaskRecords``."""
    summary = TaskRegistrySummary()
    for task in records:
        summary.total += 1
        # by_status
        setattr(summary.by_status, task.status,
                getattr(summary.by_status, task.status) + 1)
        # by_runtime
        setattr(summary.by_runtime, task.runtime,
                getattr(summary.by_runtime, task.runtime) + 1)
        if is_active_task_status(task.status):
            summary.active += 1
        else:
            summary.terminal += 1
        if is_failure_task_status(task.status):
            summary.failures += 1
    return summary


# ---------------------------------------------------------------------------
# Status snapshot (mirrors buildTaskStatusSnapshot in task-status.ts)
# ---------------------------------------------------------------------------

@dataclass
class TaskStatusSnapshot:
    latest: TaskRecord | None
    focus: TaskRecord | None
    visible: list[TaskRecord]
    active: list[TaskRecord]
    recent_terminal: list[TaskRecord]
    active_count: int
    total_count: int
    recent_failure_count: int


def build_task_status_snapshot(
    tasks: list[TaskRecord],
    now_ms: float | None = None,
) -> TaskStatusSnapshot:
    """Mirror of OpenClaw ``buildTaskStatusSnapshot``."""
    if now_ms is None:
        now_ms = time.time() * 1000
    candidates = [t for t in tasks if not is_expired_task(t, now_ms)]
    active = [t for t in candidates if is_active_task_status(t.status)]
    recent_terminal = [t for t in candidates if is_recent_terminal_task(t, now_ms)]
    visible = [*active, *recent_terminal] if active else recent_terminal
    # Focus: first active, then first recent failure, then first recent terminal
    focus: TaskRecord | None = (
        active[0] if active
        else next((t for t in recent_terminal if is_failure_task_status(t.status)), None)
        or (recent_terminal[0] if recent_terminal else None)
    )
    return TaskStatusSnapshot(
        latest=active[0] if active else (recent_terminal[0] if recent_terminal else None),
        focus=focus,
        visible=visible,
        active=active,
        recent_terminal=recent_terminal,
        active_count=len(active),
        total_count=len(visible),
        recent_failure_count=sum(1 for t in recent_terminal if is_failure_task_status(t.status)),
    )


# ---------------------------------------------------------------------------
# Audit (mirrors task-registry.audit.ts)
# ---------------------------------------------------------------------------

TaskAuditSeverity = Literal["warn", "error"]
TaskAuditCode = Literal[
    "stale_queued",
    "stale_running",
    "lost",
    "delivery_failed",
    "missing_cleanup",
    "inconsistent_timestamps",
]


@dataclass
class TaskAuditFinding:
    severity: TaskAuditSeverity
    code: TaskAuditCode
    task: TaskRecord
    age_ms: float | None
    detail: str


@dataclass
class TaskAuditSummary:
    total: int = 0
    warnings: int = 0
    errors: int = 0
    by_code: dict[str, int] = field(default_factory=lambda: {
        "stale_queued": 0, "stale_running": 0, "lost": 0,
        "delivery_failed": 0, "missing_cleanup": 0, "inconsistent_timestamps": 0,
    })


def _age_ms(task: TaskRecord, now_ms: float) -> float:
    return now_ms - (task.last_event_at or task.started_at or task.created_at)


def list_task_audit_findings(
    tasks: list[TaskRecord] | None = None,
    now_ms: float | None = None,
    stale_queued_ms: int = STALE_QUEUED_MS,
    stale_running_ms: int = STALE_RUNNING_MS,
) -> list[TaskAuditFinding]:
    """Mirror of OpenClaw ``listTaskAuditFindings``."""
    if now_ms is None:
        now_ms = time.time() * 1000
    if tasks is None:
        tasks = list_task_records()

    findings: list[TaskAuditFinding] = []

    for task in tasks:
        age = _age_ms(task, now_ms)

        # stale_queued — warn after 10 min in queue
        if task.status == "queued" and age >= stale_queued_ms:
            findings.append(TaskAuditFinding(
                severity="warn", code="stale_queued", task=task,
                age_ms=age, detail=f"Queued for {age/60000:.1f} min"
            ))

        # stale_running — error after 30 min running
        elif task.status == "running" and age >= stale_running_ms:
            findings.append(TaskAuditFinding(
                severity="error", code="stale_running", task=task,
                age_ms=age, detail=f"Running for {age/60000:.1f} min"
            ))

        # lost
        elif task.status == "lost":
            cleanup = resolve_effective_task_cleanup_after(task)
            past_cleanup = cleanup is not None and now_ms >= cleanup
            findings.append(TaskAuditFinding(
                severity="error" if past_cleanup else "warn",
                code="lost", task=task,
                age_ms=age, detail="Runtime backing state gone"
            ))

        # delivery_failed
        if (
            task.delivery_status == "failed"
            and task.notify_policy != "silent"
        ):
            findings.append(TaskAuditFinding(
                severity="warn", code="delivery_failed", task=task,
                age_ms=None, detail="Delivery failed with non-silent notify policy"
            ))

        # missing_cleanup — terminal with no cleanup_after stamped
        if is_terminal_task_status(task.status) and task.cleanup_after is None:
            derived = resolve_task_cleanup_after(task)
            if derived is not None:  # cron non-lost tasks are exempt
                findings.append(TaskAuditFinding(
                    severity="warn", code="missing_cleanup", task=task,
                    age_ms=None, detail="Terminal task missing cleanup_after timestamp"
                ))

        # inconsistent_timestamps
        if task.started_at and task.started_at < task.created_at:
            findings.append(TaskAuditFinding(
                severity="warn", code="inconsistent_timestamps", task=task,
                age_ms=None, detail="started_at is earlier than created_at"
            ))
        elif task.ended_at and task.started_at and task.ended_at < task.started_at:
            findings.append(TaskAuditFinding(
                severity="warn", code="inconsistent_timestamps", task=task,
                age_ms=None, detail="ended_at is earlier than started_at"
            ))
        elif task.status in ("queued", "running") and task.ended_at is not None:
            findings.append(TaskAuditFinding(
                severity="warn", code="inconsistent_timestamps", task=task,
                age_ms=None, detail=f"{task.status} task should not have ended_at"
            ))

    # Sort: errors first, then by age desc, then by created_at asc
    findings.sort(key=lambda f: (
        0 if f.severity == "error" else 1,
        -(f.age_ms or 0),
        f.task.created_at,
    ))
    return findings


def build_task_audit_summary(findings: list[TaskAuditFinding]) -> TaskAuditSummary:
    summary = TaskAuditSummary(total=len(findings))
    for f in findings:
        if f.severity == "error":
            summary.errors += 1
        else:
            summary.warnings += 1
        summary.by_code[f.code] = summary.by_code.get(f.code, 0) + 1
    return summary


__all__ = [
    "TaskAuditCode",
    "TaskAuditFinding",
    "TaskAuditSeverity",
    "TaskAuditSummary",
    "TaskStatusSnapshot",
    "_reset_registry_for_testing",
    "build_task_audit_summary",
    "build_task_status_snapshot",
    "find_task_by_run_id",
    "get_task_by_id",
    "list_task_audit_findings",
    "list_task_records",
    "list_tasks_for_flow",
    "list_tasks_for_owner_key",
    "list_tasks_for_session_key",
    "normalize_task_timestamps",
    "remove_task",
    "summarize_task_records",
    "upsert_task",
]
