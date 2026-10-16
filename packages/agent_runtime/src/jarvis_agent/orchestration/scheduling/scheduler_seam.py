"""Scheduler seam emitting authorized, immutable ExecutionCommands."""

from __future__ import annotations

import datetime
import uuid

from jarvis_agent.orchestration.models import ExecutionCommand, PlanNode, Task


class SchedulerSeam:
    """Bridges validated PlanNodes to the downstream tool execution subsystem."""

    @staticmethod
    def create_command(
        task: Task,
        plan_id: str,
        plan_revision: int,
        node: PlanNode,
        approval_id: str | None = None,
    ) -> ExecutionCommand:
        """Construct an immutable, idempotency-keyed ExecutionCommand for a ready node."""
        now = datetime.datetime.now(datetime.timezone.utc)
        deadline = now + datetime.timedelta(seconds=node.timeout_seconds)

        cmd_id = f"cmd_{uuid.uuid4().hex[:12]}"
        exec_id = f"exec_{uuid.uuid4().hex[:12]}"
        attempt = node.current_attempt + 1

        return ExecutionCommand.create(
            command_id=cmd_id,
            task_id=task.task_id,
            plan_id=plan_id,
            node_id=node.node_id,
            execution_id=exec_id,
            attempt_id=attempt,
            plan_revision=plan_revision,
            capability_target=node.capability,
            arguments=node.arguments,
            deadline_utc=deadline.isoformat(),
            risk_assessment=node.risk_assessment,
            approval_id=approval_id,
            issued_at_utc=now.isoformat(),
        )


__all__ = ["SchedulerSeam"]
