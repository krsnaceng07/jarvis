"""jarvis.automation.task_retention — Task retention window computation.

OpenClaw parity: mirrors
``openclaw-main/src/tasks/task-retention.ts``

Computes cleanup timestamps and pruning eligibility for the task registry.
"""

from __future__ import annotations

from .task_types import TaskRecord, TaskStatus

# ---------------------------------------------------------------------------
# Retention windows (mirrors OpenClaw constants)
# ---------------------------------------------------------------------------

# Terminal task records kept for 7 days (mirrors DEFAULT_TASK_RETENTION_MS)
DEFAULT_TASK_RETENTION_MS: int = 7 * 24 * 60 * 60 * 1000

# Lost-task records kept for only 24 hours (mirrors LOST_TASK_RETENTION_MS)
LOST_TASK_RETENTION_MS: int = 24 * 60 * 60 * 1000

# Active task stale thresholds (mirrors task-registry.audit.ts defaults)
STALE_QUEUED_MS: int = 10 * 60 * 1000   # warn after 10 min queued
STALE_RUNNING_MS: int = 30 * 60 * 1000  # error after 30 min running

# Recent-terminal window used by status snapshots (mirrors task-status.ts)
RECENT_TERMINAL_MS: int = 5 * 60 * 1000  # 5 minutes


def _resolve_task_retention_ms(status: TaskStatus) -> int:
    """Mirror of OpenClaw ``resolveTaskRetentionMs``."""
    return LOST_TASK_RETENTION_MS if status == "lost" else DEFAULT_TASK_RETENTION_MS


def resolve_task_cleanup_after(task: TaskRecord) -> float | None:
    """Mirror of OpenClaw ``resolveTaskCleanupAfter``.

    Cron tasks with non-lost status are governed by the automation history
    retention cap (CRON_HISTORY_KEEP_PER_JOB), not the per-task window.
    """
    if task.runtime == "cron" and task.status != "lost":
        return None
    terminal_at: float = task.ended_at or task.last_event_at or task.created_at
    return terminal_at + _resolve_task_retention_ms(task.status)


def resolve_effective_task_cleanup_after(task: TaskRecord) -> float | None:
    """Mirror of OpenClaw ``resolveEffectiveTaskCleanupAfter``.

    Prefers the stamped ``cleanup_after`` field when present; for lost tasks
    takes the minimum of stamped and status-derived windows.
    """
    status_cleanup = resolve_task_cleanup_after(task)
    if status_cleanup is None:
        return None
    if task.cleanup_after is None:
        return status_cleanup
    if task.status == "lost":
        return min(task.cleanup_after, status_cleanup)
    return task.cleanup_after


def is_expired_task(task: TaskRecord, now_ms: float) -> bool:
    """True when the record is past its effective cleanup window."""
    cleanup = resolve_effective_task_cleanup_after(task)
    return cleanup is not None and now_ms >= cleanup


def is_recent_terminal_task(task: TaskRecord, now_ms: float) -> bool:
    """True for terminal tasks that finished within the recent-terminal window."""
    from .task_types import is_terminal_task_status
    if not is_terminal_task_status(task.status):
        return False
    terminal_at = task.ended_at or task.last_event_at or task.created_at
    return (now_ms - terminal_at) <= RECENT_TERMINAL_MS


__all__ = [
    "DEFAULT_TASK_RETENTION_MS",
    "LOST_TASK_RETENTION_MS",
    "RECENT_TERMINAL_MS",
    "STALE_QUEUED_MS",
    "STALE_RUNNING_MS",
    "is_expired_task",
    "is_recent_terminal_task",
    "resolve_effective_task_cleanup_after",
    "resolve_task_cleanup_after",
]
