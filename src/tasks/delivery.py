"""jarvis.tasks.delivery — Delivers background task updates and terminal notifications to agent sessions.

OpenClaw parity: mirrors ``openclaw-main/src/tasks/task-registry-delivery.ts``.
Wires terminal delivery directly to ``enqueue_system_event`` and triggers reactive
``request_heartbeat`` wake-up so the agent loop immediately sees completion findings.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Set

from src.automation.task_registry import (
    get_task_by_id,
    upsert_task,
)
from src.automation.task_types import TaskRecord
from src.infra.heartbeat_wake import request_heartbeat
from src.sessions.system_event_queue import enqueue_system_event
from src.tasks.executor_policy import (
    format_task_blocked_followup_message,
    format_task_state_change_message,
    format_task_terminal_message,
    should_auto_deliver_task_state_change,
    should_auto_deliver_task_terminal_update,
    should_use_parent_review_task_terminal_message,
)

logger = logging.getLogger("jarvis.tasks.delivery")

_tasks_with_pending_delivery: Set[str] = set()


def queue_task_system_event(
    task: TaskRecord,
    text: str,
    owner_key: str,
    agent_id: Optional[str] = None,
    source: str = "background-task",
) -> bool:
    """Enqueue a system event for the task owner session and request reactive heartbeat wake."""
    owner_session_key = owner_key.strip() if owner_key else None
    if not owner_session_key:
        return False

    context_key = f"task:{task.task_id}"
    if source == "background-task-blocked":
        context_key += ":blocked-followup"

    options: dict[str, Any] = {
        "sessionKey": owner_session_key,
        "contextKey": context_key,
    }
    if agent_id:
        options["agentId"] = agent_id

    try:
        enqueue_system_event(text, options)
    except Exception as exc:
        logger.warning("Failed to enqueue system event for task %s: %s", task.task_id, exc)
        return False

    try:
        request_heartbeat({
            "source": source,
            "intent": "immediate",
            "reason": source,
            "sessionKey": owner_session_key,
            "agentId": agent_id or task.agent_id,
        })
    except Exception as exc:
        logger.warning("Failed to request heartbeat wake for task %s: %s", task.task_id, exc)

    return True


def maybe_deliver_task_terminal_update(task_id: str) -> Optional[TaskRecord]:
    """Check task eligibility and deliver terminal completion message to the owner session."""
    current = get_task_by_id(task_id)
    if not current or not should_auto_deliver_task_terminal_update(current):
        return current

    if task_id in _tasks_with_pending_delivery:
        return current

    _tasks_with_pending_delivery.add(task_id)
    try:
        latest = get_task_by_id(task_id)
        if not latest or not should_auto_deliver_task_terminal_update(latest):
            return latest

        owner_key = (latest.owner_key or "").strip()
        if not owner_key:
            # Missing owner, cannot deliver
            import dataclasses
            updated = dataclasses.replace(
                latest,
                delivery_status="not_applicable",
                last_event_at=int(time.time() * 1000),
            )
            upsert_task(updated)
            return updated

        should_route_parent = should_use_parent_review_task_terminal_message(latest)
        session_event_text = format_task_terminal_message(
            latest,
            options={"surface": "parent_session"} if should_route_parent else None,
        )

        import dataclasses
        success = queue_task_system_event(
            latest,
            session_event_text,
            owner_key=owner_key,
            agent_id=latest.agent_id or latest.requester_agent_id,
            source="background-task",
        )

        if latest.terminal_outcome == "blocked":
            followup = format_task_blocked_followup_message(latest)
            if followup:
                queue_task_system_event(
                    latest,
                    followup,
                    owner_key=owner_key,
                    agent_id=latest.agent_id or latest.requester_agent_id,
                    source="background-task-blocked",
                )

        updated = dataclasses.replace(
            latest,
            delivery_status="session_queued" if success else "failed",
            last_event_at=int(time.time() * 1000),
        )
        upsert_task(updated)
        return updated
    finally:
        _tasks_with_pending_delivery.discard(task_id)


def maybe_deliver_task_state_change_update(
    task_id: str,
    event: Any,
) -> Optional[TaskRecord]:
    """Deliver a non-terminal state change update if notify_policy is 'state_changes'."""
    current = get_task_by_id(task_id)
    if not current or not should_auto_deliver_task_state_change(current):
        return current

    owner_key = (current.owner_key or "").strip()
    if not owner_key:
        return current

    msg = format_task_state_change_message(current, event)
    if not msg:
        return current

    queue_task_system_event(
        current,
        msg,
        owner_key=owner_key,
        agent_id=current.agent_id or current.requester_agent_id,
        source="background-task",
    )
    return current


__all__ = [
    "maybe_deliver_task_state_change_update",
    "maybe_deliver_task_terminal_update",
    "queue_task_system_event",
]
