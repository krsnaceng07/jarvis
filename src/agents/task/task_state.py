"""jarvis.agents.task.task_state — Continuous task tracking and execution state.

Enables continuous multi-step tasks without losing context:
  CREATED → PLANNING → RUNNING → VERIFYING → COMPLETED (or FAILED / CANCELLED)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ..verification.execution_record import ExecutionRecord
from ..verification.execution_verifier import VerificationOutcome


@dataclass(slots=True)
class TaskStep:
    """A single discrete step in a multi-step task."""

    step_index: int
    description: str
    status: str = "pending"  # "pending" | "running" | "completed" | "failed"
    tool_name: Optional[str] = None
    execution_record: Optional[ExecutionRecord] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.execution_record:
            data["execution_record"] = self.execution_record.to_dict()
        return data


@dataclass(slots=True)
class TaskState:
    """State machine and execution context for an active task."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    status: str = "RUNNING"  # CREATED, PLANNING, RUNNING, VERIFYING, COMPLETED, FAILED, CANCELLED
    current_step_index: int = 0
    steps: list[TaskStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    modified_files: list[str] = field(default_factory=list)
    execution_history: list[ExecutionRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "current_step_index": self.current_step_index,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "modified_files": list(self.modified_files),
            "execution_history": [e.to_dict() for e in self.execution_history],
        }


class TaskStateManager:
    """Singleton/registry managing active task lifecycle and execution continuity."""

    _instance: Optional[TaskStateManager] = None

    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}
        self._active_task_id: Optional[str] = None
        self._global_execution_history: list[ExecutionRecord] = []

    @classmethod
    def get_instance(cls) -> TaskStateManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_task(
        self,
        goal: str,
        steps: Optional[list[str]] = None,
        task_id: Optional[str] = None,
    ) -> TaskState:
        """Create and activate a new task."""
        tid = task_id or str(uuid.uuid4())
        step_objs = []
        if steps:
            for idx, desc in enumerate(steps, start=1):
                step_objs.append(TaskStep(step_index=idx, description=desc))

        task = TaskState(
            task_id=tid,
            goal=goal,
            status="RUNNING" if step_objs else "PLANNING",
            steps=step_objs,
            current_step_index=1 if step_objs else 0,
        )
        self._tasks[tid] = task
        self._active_task_id = tid
        return task

    def get_active_task(self) -> Optional[TaskState]:
        if self._active_task_id and self._active_task_id in self._tasks:
            return self._tasks[self._active_task_id]
        return None

    def record_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_output: str,
        status: str = "success",
        verification: Optional[VerificationOutcome] = None,
        affected_files: Optional[list[str]] = None,
        session_key: str = "agent:main:main",
    ) -> ExecutionRecord:
        """Record an executed tool action, updating active task state."""
        active = self.get_active_task()
        files = list(affected_files or [])

        record = ExecutionRecord(
            task_id=active.task_id if active else None,
            session_key=session_key,
            tool_name=tool_name,
            arguments=arguments,
            status=status,
            raw_output=raw_output,
            verification=verification,
            affected_files=files,
        )

        self._global_execution_history.append(record)
        # Keep global history bounded
        if len(self._global_execution_history) > 100:
            self._global_execution_history = self._global_execution_history[-100:]

        if active:
            active.execution_history.append(record)
            active.updated_at = time.time()
            for f in files:
                if f not in active.modified_files:
                    active.modified_files.append(f)

            # Associate with current step if running
            if active.steps and 1 <= active.current_step_index <= len(active.steps):
                step = active.steps[active.current_step_index - 1]
                step.tool_name = tool_name
                step.execution_record = record
                if status == "success" and verification is not None and verification.is_success:
                    step.status = "completed"
                elif status == "failed":
                    step.status = "failed"
                else:
                    step.status = "running"

        return record

    def advance_step(self, next_step_index: Optional[int] = None) -> Optional[TaskState]:
        """Advance to the next step of the active task."""
        active = self.get_active_task()
        if not active or not active.steps:
            return active

        if active.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return active
        current = active.current_step_index
        if not 1 <= current <= len(active.steps):
            raise ValueError("Current task step is out of range")
        # Advancing is a verified transition, not a way to skip pending work.
        # Otherwise repeated calls can manufacture a completed task without tools.
        if active.steps[current - 1].status != "completed":
            return active
        if next_step_index is not None and next_step_index != current + 1:
            raise ValueError("Can only advance to the next verified task step")

        if next_step_index is not None:
            active.current_step_index = next_step_index
        else:
            active.current_step_index += 1

        active.updated_at = time.time()
        if active.current_step_index > len(active.steps):
            active.status = "COMPLETED"
        else:
            active.status = "RUNNING"
            active.steps[active.current_step_index - 1].status = "running"

        return active

    def get_last_execution_record(self) -> Optional[ExecutionRecord]:
        if self._global_execution_history:
            return self._global_execution_history[-1]
        return None

    def format_task_context_for_prompt(self) -> str:
        """Format the active task and recent executions into a model-visible prompt block."""
        active = self.get_active_task()
        last_record = self.get_last_execution_record()

        lines = ["[CONTINUOUS TASK CONTEXT]"]

        if active:
            lines.append(f"Active Goal: {active.goal}")
            lines.append(f"Task Status: {active.status}")
            if active.steps:
                lines.append(
                    f"Current Step: Step {active.current_step_index} of {len(active.steps)}"
                )
                for s in active.steps:
                    marker = (
                        "▶"
                        if s.step_index == active.current_step_index
                        else ("✓" if s.status == "completed" else " ")
                    )
                    lines.append(f"  [{marker}] Step {s.step_index}: {s.description} ({s.status})")
            if active.modified_files:
                lines.append(f"Modified Files: {', '.join(active.modified_files)}")
        else:
            lines.append("No active multi-step task currently set.")

        if last_record:
            verif_info = (
                " [Verified]"
                if last_record.verification and last_record.verification.verified
                else ""
            )
            lines.append(
                f"Most Recent Action: [{last_record.tool_name}] status={last_record.status}{verif_info} "
                f"at {time.strftime('%H:%M:%S', time.localtime(last_record.timestamp))}"
            )
            out_preview = last_record.raw_output.strip().replace("\n", " ")[:160]
            lines.append(f"Last Action Output: {out_preview}")
        else:
            lines.append("No actions executed in this session yet.")

        lines.append(
            "Continuity Directive: Always ground your replies in the active task context "
            "and execution history above. When the user asks to continue, proceed with "
            "the next pending step based on real outcomes."
        )

        return "\n".join(lines) + "\n"
