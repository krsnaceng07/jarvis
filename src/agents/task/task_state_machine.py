"""jarvis.agents.task.task_state_machine — Explicit multi-stage task workflow machine.

Enforces structured, observable progress through predefined task stages.
Prevents jumping from action execution directly to task completion without
intervening observation and authoritative verification.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .runtime_state import RuntimeStateManager, TaskStatus


@dataclass(slots=True)
class TaskStage:
    """A discrete, observable stage in a task workflow."""

    stage_id: str
    name: str
    description: str
    is_mutation: bool = False
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, executing, observing, verified, failed, skipped
    result: Optional[dict[str, Any]] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class TaskStateMachine:
    """State machine governing explicit step-by-step task progression."""

    def __init__(self, task_name: str, stages: list[TaskStage], task_id: Optional[str] = None) -> None:
        self.task_name = task_name
        self.stages = {s.stage_id: s for s in stages}
        self.stage_order = [s.stage_id for s in stages]
        self.current_stage_index: int = 0
        self.state_mgr = RuntimeStateManager.get_instance()
        if task_id:
            self.state_mgr.state.active_task_id = task_id
        self.state_mgr.state.pending_stages = list(self.stage_order)
        self.state_mgr.state.completed_stages = []
        self.state_mgr.state.failed_stages = []

    @property
    def current_stage(self) -> Optional[TaskStage]:
        if 0 <= self.current_stage_index < len(self.stage_order):
            sid = self.stage_order[self.current_stage_index]
            return self.stages.get(sid)
        return None

    def advance_stage(
        self,
        verified: bool = True,
        result: Optional[dict[str, Any]] = None,
        already_completed: bool = False,
    ) -> Optional[TaskStage]:
        """Advance to the next sequential stage upon verification."""
        curr = self.current_stage
        if not curr:
            return None

        now = time.time()
        curr.completed_at = now
        curr.result = result

        if already_completed:
            curr.status = "skipped"
            self.state_mgr.transition_stage(
                new_stage=f"{curr.stage_id}_already_completed",
                status=TaskStatus.ALREADY_COMPLETED,
                verified=True,
            )
            return None

        if verified:
            curr.status = "verified"
            self.state_mgr.transition_stage(
                new_stage=curr.stage_id,
                status=TaskStatus.VERIFYING,
                verified=True,
            )
        else:
            curr.status = "failed"
            self.state_mgr.transition_stage(
                new_stage=curr.stage_id,
                status=TaskStatus.FAILED,
                verified=False,
            )
            return None

        self.current_stage_index += 1
        nxt = self.current_stage
        if nxt:
            nxt.started_at = now
            nxt.status = "executing"
            self.state_mgr.transition_stage(
                new_stage=nxt.stage_id,
                status=TaskStatus.EXECUTING,
                verified=False,
            )
        else:
            # All stages verified
            self.state_mgr.record_verified_result(
                status=TaskStatus.COMPLETED_VERIFIED,
                verification_details={"final_stage": curr.stage_id, "summary": "All stages verified"},
            )

        return nxt

    def fail_current_stage(self, error: str, details: Optional[dict[str, Any]] = None) -> None:
        """Mark current stage as failed."""
        curr = self.current_stage
        if curr:
            curr.status = "failed"
            curr.completed_at = time.time()
            curr.result = {"error": error, "details": details or {}}
            self.state_mgr.record_verified_result(
                status=TaskStatus.FAILED,
                verification_details={"stage": curr.stage_id, "error": error},
            )


def create_youtube_subscription_workflow() -> TaskStateMachine:
    """Standard 13-stage workflow for YouTube subscription (Prompt parity)."""
    stages = [
        TaskStage("stage_1", "identify_user_target", "Identify user target channel"),
        TaskStage("stage_2", "resolve_browser_session", "Resolve active browser session"),
        TaskStage("stage_3", "resolve_correct_tab", "Resolve correct YouTube tab"),
        TaskStage("stage_4", "inspect_current_page", "Inspect current page state & URL"),
        TaskStage("stage_5", "identify_target_channel", "Identify target channel on page"),
        TaskStage("stage_6", "inspect_subscription_state", "Inspect current subscription state"),
        TaskStage("stage_7", "check_already_subscribed", "Determine whether already subscribed"),
        TaskStage("stage_8", "locate_subscribe_control", "Locate current Subscribe control"),
        TaskStage("stage_9", "execute_click", "Execute Subscribe click", is_mutation=True),
        TaskStage("stage_10", "observe_post_click", "Observe page state after click"),
        TaskStage("stage_11", "verify_subscription_change", "Verify subscription state transitioned to Subscribed"),
        TaskStage("stage_12", "mark_completed_verified", "Mark task completed_verified"),
        TaskStage("stage_13", "report_result", "Generate truthful final report with evidence"),
    ]
    return TaskStateMachine("youtube_subscribe", stages)
