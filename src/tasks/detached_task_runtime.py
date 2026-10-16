"""jarvis.tasks.detached_task_runtime — Runtime adapter for detached task execution.

OpenClaw parity: mirrors ``openclaw-main/src/tasks/detached-task-runtime.ts``.
Provides standard task creation, progress tracking, and finalization for background work,
connecting background jobs and CLI executions into the canonical task registry and
triggering reactive terminal deliveries.
"""

from __future__ import annotations

import dataclasses
import logging
import time
import uuid
from typing import Any, Optional

from src.automation.task_registry import (
    find_task_by_run_id as _find_task_by_run_id,
    list_task_records,
    upsert_task,
)
from src.automation.task_types import (
    DEFAULT_NOTIFY_POLICY_BY_RUNTIME,
    TaskDeliveryStatus,
    TaskNotifyPolicy,
    TaskRecord,
    TaskRuntime,
    TaskScopeKind,
    TaskStatus,
    TaskTerminalOutcome,
)
from src.tasks.delivery import (
    maybe_deliver_task_state_change_update,
    maybe_deliver_task_terminal_update,
)

logger = logging.getLogger("jarvis.tasks.detached_runtime")


def create_running_task_run(
    runtime: TaskRuntime,
    task_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    requester_session_key: str = "agent:main:main",
    owner_key: Optional[str] = None,
    scope_kind: TaskScopeKind = "session",
    agent_id: Optional[str] = None,
    requester_agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    label: Optional[str] = None,
    task: str = "Background task",
    notify_policy: Optional[TaskNotifyPolicy] = None,
    started_at: Optional[float] = None,
    last_event_at: Optional[float] = None,
    progress_summary: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> TaskRecord:
    """Create and register a running task record in the task registry."""
    now_ms = time.time() * 1000.0
    effective_started_at = started_at or now_ms
    effective_owner_key = owner_key or requester_session_key
    effective_notify_policy: TaskNotifyPolicy = (
        notify_policy or DEFAULT_NOTIFY_POLICY_BY_RUNTIME.get(runtime, "done_only")  # type: ignore[assignment]
    )
    delivery_status: TaskDeliveryStatus = (
        "pending" if effective_notify_policy != "silent" else "not_applicable"
    )

    task_id = str(uuid.uuid4())
    record = TaskRecord(
        task_id=task_id,
        runtime=runtime,
        task_kind=task_kind,
        source_id=source_id,
        requester_session_key=requester_session_key,
        owner_key=effective_owner_key,
        scope_kind=scope_kind,
        agent_id=agent_id,
        requester_agent_id=requester_agent_id,
        run_id=run_id,
        label=label,
        task=task,
        status="running",
        delivery_status=delivery_status,
        notify_policy=effective_notify_policy,
        created_at=now_ms,
        started_at=effective_started_at,
        last_event_at=last_event_at or effective_started_at,
        progress_summary=progress_summary,
        detail=detail,
    )

    upsert_task(record)
    logger.info("Registered running task: id=%s run_id=%s label=%s", task_id, run_id, label)
    return record


def create_queued_task_run(
    runtime: TaskRuntime,
    task_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    requester_session_key: str = "agent:main:main",
    owner_key: Optional[str] = None,
    scope_kind: TaskScopeKind = "session",
    agent_id: Optional[str] = None,
    requester_agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    label: Optional[str] = None,
    task: str = "Background task",
    notify_policy: Optional[TaskNotifyPolicy] = None,
    detail: Optional[dict[str, Any]] = None,
) -> TaskRecord:
    """Create and register a queued task record in the task registry."""
    now_ms = time.time() * 1000.0
    effective_owner_key = owner_key or requester_session_key
    effective_notify_policy: TaskNotifyPolicy = (
        notify_policy or DEFAULT_NOTIFY_POLICY_BY_RUNTIME.get(runtime, "done_only")  # type: ignore[assignment]
    )
    delivery_status: TaskDeliveryStatus = (
        "pending" if effective_notify_policy != "silent" else "not_applicable"
    )

    task_id = str(uuid.uuid4())
    record = TaskRecord(
        task_id=task_id,
        runtime=runtime,
        task_kind=task_kind,
        source_id=source_id,
        requester_session_key=requester_session_key,
        owner_key=effective_owner_key,
        scope_kind=scope_kind,
        agent_id=agent_id,
        requester_agent_id=requester_agent_id,
        run_id=run_id,
        label=label,
        task=task,
        status="queued",
        delivery_status=delivery_status,
        notify_policy=effective_notify_policy,
        created_at=now_ms,
        started_at=None,
        last_event_at=now_ms,
        detail=detail,
    )

    upsert_task(record)
    logger.info("Registered queued task: id=%s run_id=%s label=%s", task_id, run_id, label)
    return record


def start_task_run_by_run_id(
    run_id: str,
    started_at: Optional[float] = None,
    progress_summary: Optional[str] = None,
) -> list[TaskRecord]:
    """Transition tasks matching run_id from queued to running."""
    now_ms = time.time() * 1000.0
    matching = [t for t in list_task_records() if t.run_id == run_id]
    updated_records: list[TaskRecord] = []
    for task in matching:
        updated = dataclasses.replace(
            task,
            status="running",
            started_at=started_at or task.started_at or now_ms,
            last_event_at=now_ms,
            progress_summary=progress_summary or task.progress_summary,
        )
        upsert_task(updated)
        updated_records.append(updated)
        maybe_deliver_task_state_change_update(updated.task_id, "running")
    return updated_records


def record_task_run_progress_by_run_id(
    run_id: str,
    progress_summary: str,
    last_event_at: Optional[float] = None,
) -> list[TaskRecord]:
    """Record progress on tasks matching run_id."""
    now_ms = last_event_at or (time.time() * 1000.0)
    matching = [t for t in list_task_records() if t.run_id == run_id]
    updated_records: list[TaskRecord] = []
    for task in matching:
        updated = dataclasses.replace(
            task,
            progress_summary=progress_summary,
            last_event_at=now_ms,
        )
        upsert_task(updated)
        updated_records.append(updated)
    return updated_records


def finalize_task_run_by_run_id(
    run_id: str,
    status: TaskStatus = "succeeded",
    runtime: Optional[TaskRuntime] = None,
    session_key: Optional[str] = None,
    ended_at: Optional[float] = None,
    last_event_at: Optional[float] = None,
    terminal_summary: Optional[str] = None,
    terminal_outcome: Optional[TaskTerminalOutcome] = None,
    error: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    suppress_delivery: bool = False,
) -> list[TaskRecord]:
    """Finalize all task records matching run_id and trigger terminal delivery."""
    now_ms = time.time() * 1000.0
    effective_ended_at = ended_at or now_ms
    effective_last_event_at = last_event_at or effective_ended_at

    matching = [
        t for t in list_task_records()
        if t.run_id == run_id
        and (runtime is None or t.runtime == runtime)
        and (session_key is None or t.owner_key == session_key or t.requester_session_key == session_key)
    ]

    if not matching:
        logger.debug("finalize_task_run_by_run_id found no matching tasks for run_id=%s", run_id)
        return []

    updated_records: list[TaskRecord] = []
    for task in matching:
        delivery_status: TaskDeliveryStatus = (
            "not_applicable"
            if (suppress_delivery or task.notify_policy == "silent")
            else "pending"
        )
        new_detail = dict(task.detail or {})
        if detail:
            new_detail.update(detail)

        updated = dataclasses.replace(
            task,
            status=status,
            ended_at=effective_ended_at,
            last_event_at=effective_last_event_at,
            terminal_summary=terminal_summary,
            terminal_outcome=terminal_outcome,
            error=error,
            delivery_status=delivery_status,
            detail=new_detail or None,
        )
        upsert_task(updated)
        updated_records.append(updated)

        if not suppress_delivery:
            maybe_deliver_task_terminal_update(updated.task_id)

    logger.info(
        "Finalized %d task(s) for run_id=%s status=%s",
        len(updated_records),
        run_id,
        status,
    )
    return updated_records


def complete_task_run_by_run_id(
    run_id: str,
    ended_at: Optional[float] = None,
    terminal_summary: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> list[TaskRecord]:
    return finalize_task_run_by_run_id(
        run_id=run_id,
        status="succeeded",
        ended_at=ended_at,
        terminal_summary=terminal_summary or "Task completed successfully",
        detail=detail,
    )


def fail_task_run_by_run_id(
    run_id: str,
    status: TaskStatus = "failed",
    ended_at: Optional[float] = None,
    error: Optional[str] = None,
    terminal_summary: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> list[TaskRecord]:
    return finalize_task_run_by_run_id(
        run_id=run_id,
        status=status,
        ended_at=ended_at,
        error=error,
        terminal_summary=terminal_summary or error or "Task failed",
        detail=detail,
    )


def find_task_by_run_id(run_id: str) -> Optional[TaskRecord]:
    return _find_task_by_run_id(run_id)


__all__ = [
    "complete_task_run_by_run_id",
    "create_queued_task_run",
    "create_running_task_run",
    "fail_task_run_by_run_id",
    "finalize_task_run_by_run_id",
    "find_task_by_run_id",
    "record_task_run_progress_by_run_id",
    "start_task_run_by_run_id",
]
