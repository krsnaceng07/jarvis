"""jarvis.tasks.executor_policy — Decides task executor delivery, terminal update, and follow-up message policy.

OpenClaw parity: mirrors ``openclaw-main/src/tasks/task-executor-policy.ts``.
"""

from __future__ import annotations

from typing import Any, Optional
from src.automation.task_types import (
    TaskRecord,
    is_terminal_task_status,
)

SUBAGENT_KILL_TASK_ERROR = "Subagent killed by operator"


def resolve_task_display_title(task: TaskRecord) -> str:
    """Format human-readable title for a task record."""
    if task.label and task.label.strip():
        return task.label.strip()
    if task.runtime == "acp":
        return "ACP background task"
    if task.runtime == "subagent":
        return "Subagent task"
    if task.task and task.task.strip():
        return task.task.strip()
    return "Background task"


def resolve_task_run_label(task: TaskRecord) -> str:
    """Format run label identifier."""
    if task.run_id and task.run_id.strip():
        return f" (run {task.run_id.strip()[:8]})"
    return ""


def sanitize_task_status_text(text: Optional[str], error_context: bool = False) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    return cleaned


def format_task_terminal_message(
    task: TaskRecord,
    options: Optional[dict[str, Any]] = None,
) -> str:
    """Format the canonical user/system event notification when a task reaches a terminal status."""
    options = options or {}
    title = resolve_task_display_title(task)
    run_label = resolve_task_run_label(task)
    summary = sanitize_task_status_text(
        task.terminal_summary,
        error_context=(task.status != "succeeded" or task.terminal_outcome == "blocked"),
    )

    if task.status == "succeeded":
        if task.terminal_outcome == "blocked":
            return (
                f"Background task blocked: {title}{run_label}. {summary}"
                if summary
                else f"Background task blocked: {title}{run_label}."
            )
        if options.get("surface") == "parent_session":
            review_next = "Next: parent will review/verify before calling it done."
            return (
                f"Background task ready for review: {title}{run_label}. {summary} {review_next}"
                if summary
                else f"Background task ready for review: {title}{run_label}. {review_next}"
            )
        return (
            f"Background task done: {title}{run_label}. {summary}"
            if summary
            else f"Background task done: {title}{run_label}."
        )

    if task.status == "timed_out":
        return f"Background task timed out: {title}{run_label}."

    if task.status == "lost":
        err = sanitize_task_status_text(task.error, error_context=True)
        fallback = sanitize_task_status_text(task.terminal_summary, error_context=True)
        reason = err or fallback or "Backing session disappeared."
        return f"Background task lost: {title}{run_label}. {reason}"

    if task.status == "cancelled":
        if task.runtime == "subagent":
            return f"Background task cancellation requested: {title}{run_label}."
        return f"Background task cancelled: {title}{run_label}."

    # Failed
    err = sanitize_task_status_text(task.error, error_context=True)
    fallback = sanitize_task_status_text(task.terminal_summary, error_context=True)
    if err:
        return f"Background task failed: {title}{run_label}. {err}"
    if fallback:
        return f"Background task failed: {title}{run_label}. {fallback}"
    return f"Background task failed: {title}{run_label}."


def should_use_parent_review_task_terminal_message(task: TaskRecord) -> bool:
    return (
        task.runtime == "acp"
        and task.status == "succeeded"
        and task.terminal_outcome != "blocked"
        and bool(task.child_session_key and task.child_session_key.strip())
    )


def format_task_blocked_followup_message(task: TaskRecord) -> Optional[str]:
    if task.status != "succeeded" or task.terminal_outcome != "blocked":
        return None
    title = resolve_task_display_title(task)
    run_label = resolve_task_run_label(task)
    summary = (
        sanitize_task_status_text(task.terminal_summary, error_context=True)
        or "Task is blocked and needs follow-up."
    )
    return f"Task needs follow-up: {title}{run_label}. {summary}"


def format_task_state_change_message(task: TaskRecord, event: Any) -> Optional[str]:
    title = resolve_task_display_title(task)
    kind = getattr(event, "kind", str(event))
    if kind == "running":
        return f"Background task started: {title}."
    if kind == "progress":
        summary = sanitize_task_status_text(getattr(event, "summary", ""))
        return f"Background task update: {title}. {summary}" if summary else None
    return None


def should_auto_deliver_task_terminal_update(task: TaskRecord) -> bool:
    """Return True if this task terminal transition should be delivered to the session."""
    if task.notify_policy == "silent":
        return False
    if task.runtime == "subagent" and task.status != "cancelled":
        return False
    if (
        task.runtime == "subagent"
        and task.status == "cancelled"
        and task.error == SUBAGENT_KILL_TASK_ERROR
    ):
        return False
    if not is_terminal_task_status(task.status):
        return False
    return task.delivery_status == "pending"


def should_auto_deliver_task_state_change(task: TaskRecord) -> bool:
    return (
        task.notify_policy == "state_changes"
        and task.delivery_status == "pending"
        and not is_terminal_task_status(task.status)
    )


def should_suppress_duplicate_terminal_delivery(
    task: TaskRecord,
    preferred_task_id: Optional[str] = None,
    peer_delivery_cover: bool = False,
) -> bool:
    if not task.run_id or not task.run_id.strip():
        return False
    shares_run_delivery = task.runtime == "acp" or (
        task.runtime == "subagent" and task.status == "cancelled"
    )
    if not shares_run_delivery:
        return False
    if task.runtime == "subagent" and peer_delivery_cover:
        return True
    return bool(preferred_task_id and preferred_task_id != task.task_id)


__all__ = [
    "SUBAGENT_KILL_TASK_ERROR",
    "format_task_blocked_followup_message",
    "format_task_state_change_message",
    "format_task_terminal_message",
    "is_terminal_task_status",
    "resolve_task_display_title",
    "resolve_task_run_label",
    "should_auto_deliver_task_state_change",
    "should_auto_deliver_task_terminal_update",
    "should_suppress_duplicate_terminal_delivery",
    "should_use_parent_review_task_terminal_message",
]
