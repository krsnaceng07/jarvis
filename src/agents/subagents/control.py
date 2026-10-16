"""src.agents.subagents.control
Subagent tree control, cancellation cascade, and introspection.

Matches OpenClaw parity:
- src/agents/subagents/registry/subagent-control-kill.ts
- src/agents/subagents/registry/subagent-control.ts
- src/agents/tools/subagents-tool.ts
"""

from __future__ import annotations

import time
from typing import Any

from .capabilities import can_control_children
from .registry import SubagentRegistry
from .spawner import SubagentSpawner
from .types import SubagentRole, SubagentRunRecord, SubagentStatus


class SubagentController:
    """Provides session tree introspection and cascading cancellation."""

    def __init__(
        self,
        registry: SubagentRegistry | None = None,
        spawner: SubagentSpawner | None = None,
    ) -> None:
        self.registry = registry or SubagentRegistry.get_instance()
        self.spawner = spawner

    def list_controlled_runs(
        self,
        controller_session_key: str,
        recent_minutes: int = 30,
    ) -> list[dict[str, Any]]:
        """List all active or recent subagent runs under the caller's session tree."""
        runs = self.registry.list_controlled_runs(controller_session_key)
        cutoff = time.time() - (recent_minutes * 60.0)

        results: list[dict[str, Any]] = []
        for r in runs:
            # Include active tasks or tasks ended within recent_minutes
            if (
                r.status in (SubagentStatus.QUEUED, SubagentStatus.RUNNING)
                or (r.ended_at and r.ended_at >= cutoff)
                or r.started_at >= cutoff
            ):
                results.append(
                    {
                        "taskId": r.task_id or r.run_id,
                        "runId": r.run_id,
                        "childSessionKey": r.child_session_key,
                        "parentSessionKey": r.parent_session_key,
                        "task": r.task,
                        "label": r.label,
                        "role": r.role.value,
                        "depth": r.depth,
                        "status": r.status.value,
                        "startedAt": r.started_at,
                        "endedAt": r.ended_at,
                        "error": r.error,
                        "resultSummary": (r.result_text[:120] + "…")
                        if r.result_text and len(r.result_text) > 120
                        else r.result_text,
                    }
                )

        # Sort newest first
        results.sort(key=lambda x: float(x.get("startedAt") or 0.0), reverse=True)
        return results

    def cancel_run(
        self,
        task_id_or_run_id: str,
        caller_session_key: str = "desktop:hud",
        caller_role: SubagentRole = SubagentRole.MAIN,
    ) -> tuple[bool, str]:
        """Cancel a subagent task and recursively cancel all its descendants."""
        # 1. Find target run
        target_run: SubagentRunRecord | None = None
        for rec in self.registry._runs_by_id.values():
            if rec.run_id == task_id_or_run_id or rec.task_id == task_id_or_run_id:
                target_run = rec
                break

        if not target_run:
            target_run = self.registry.get_run(task_id_or_run_id)

        if not target_run:
            return False, f"Task '{task_id_or_run_id}' not found in registry."

        # 2. Permission check: leaf cannot cancel other sessions
        if caller_role == SubagentRole.LEAF and not can_control_children(caller_role):
            if target_run.child_session_key != caller_session_key:
                return False, "Leaf subagents cannot cancel other sessions."

        # 3. Cancel the target in spawner if active
        if self.spawner:
            self.spawner.cancel_task(target_run.run_id)

        self.registry.update_run_status(
            target_run.run_id,
            SubagentStatus.CANCELLED,
            error="Cancelled by controller or parent session.",
        )

        # 4. Recursively cancel all descendants
        descendant_keys = self.registry.get_descendant_keys(target_run.child_session_key)
        for d_key in descendant_keys:
            d_rec = self.registry.get_run(d_key)
            if d_rec:
                if self.spawner:
                    self.spawner.cancel_task(d_rec.run_id)
                self.registry.update_run_status(
                    d_rec.run_id,
                    SubagentStatus.CANCELLED,
                    error=f"Cascading cancellation from parent task '{target_run.task_id or target_run.run_id}'.",
                )

        return (
            True,
            f"Task '{target_run.task_id or target_run.run_id}' and {len(descendant_keys)} descendant(s) cancelled.",
        )
