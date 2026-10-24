"""src.agents.subagents.spawner
Subagent spawner and lifecycle admission engine.

Matches OpenClaw parity:
- src/agents/subagents/spawn/subagent-spawn.ts
- src/agents/subagents/spawn/subagent-spawn-contract.ts
- src/agents/subagents/spawn/subagent-task-name.ts
- src/agents/tools/sessions-spawn-tool.ts
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Callable, Coroutine

from .capabilities import (
    DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH,
    can_spawn_subagents,
    resolve_subagent_role,
)
from .registry import SubagentRegistry
from .types import (
    SpawnSubagentParams,
    SpawnSubagentResult,
    SubagentRole,
    SubagentRunRecord,
    SubagentStatus,
)


def normalize_task_name(name: str | None) -> tuple[str, str | None]:
    """Validate and normalize a stable task name alias.

    Must start with lowercase letter, followed by lowercase alphanumeric, hyphens, or underscores.
    """
    if not name:
        return "", None
    trimmed = name.strip()
    if not trimmed:
        return "", None
    if not re.match(r"^[a-z][a-z0-9_-]*$", trimmed):
        return (
            "",
            "Invalid taskName: must start with a lowercase letter and contain only lowercase letters, digits, hyphen, or underscore.",
        )
    return trimmed, None


class SubagentSpawner:
    """Core spawner responsible for validating, admitting, and launching subagent sessions."""

    def __init__(
        self,
        registry: SubagentRegistry | None = None,
        tool_provider: Callable[[SubagentRole], dict[str, Any]] | None = None,
    ) -> None:
        self.registry = registry or SubagentRegistry.get_instance()
        self.tool_provider = tool_provider
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._completion_listeners: list[Callable[[SubagentRunRecord, str | None], None]] = []

    def register_completion_listener(
        self,
        listener: Callable[[SubagentRunRecord, str | None], None],
    ) -> None:
        """Register a callback for child completion events (OpenClaw parity)."""
        if listener not in self._completion_listeners:
            self._completion_listeners.append(listener)

    def _dispatch_completion(self, record: SubagentRunRecord) -> None:
        """Deliver child completion findings to registered listeners and system event queues."""
        from .completion import build_child_completion_findings

        findings = build_child_completion_findings([record])
        for listener in self._completion_listeners:
            try:
                listener(record, findings)
            except Exception:
                pass

        try:
            from src.sessions.system_event_queue import enqueue_system_event
            from src.infra.heartbeat_wake import request_heartbeat

            target_session = record.parent_session_key or "agent:main:main"
            label = record.label or record.task or record.task_id
            status_val = (
                record.status.value
                if hasattr(record.status, "value")
                else str(record.status)
            )
            event_text = f"Subagent task '{label}' finished with status: {status_val}."
            if record.error:
                event_text += f" Error: {record.error}"
            elif findings:
                findings_summary = findings.strip()
                if len(findings_summary) > 300:
                    findings_summary = findings_summary[:300] + "..."
                event_text += f"\nFindings:\n{findings_summary}"

            enqueue_system_event(
                event_text,
                {"sessionKey": "desktop:hud", "contextKey": f"subagent:{record.run_id}"},
            )
            enqueue_system_event(
                event_text,
                {"sessionKey": target_session, "contextKey": f"subagent:{record.run_id}"},
            )
            if target_session != "agent:main:main":
                enqueue_system_event(
                    event_text,
                    {"sessionKey": "agent:main:main", "contextKey": f"subagent:{record.run_id}"},
                )
            request_heartbeat({
                "source": "subagent_completion",
                "intent": "immediate",
                "reason": "subagent_completion",
                "sessionKey": target_session,
                "runId": record.run_id,
            })
        except Exception as e:
            print(f"[SubagentSpawner] Error dispatching completion event: {e}")

    async def spawn(
        self,
        params: SpawnSubagentParams,
        runner_factory: (
            Callable[[SubagentRunRecord, dict[str, Any]], Coroutine[Any, Any, None]] | None
        ) = None,
    ) -> SpawnSubagentResult:
        """Admit and spawn a subagent run.

        Enforces depth limits, role constraints, and creates background worker tasks.
        """
        # 1. Validate task description
        if not params.task or not params.task.strip():
            return SpawnSubagentResult(
                status="error",
                error="Subagent task description is required and cannot be empty.",
            )

        # 2. Check depth and role constraints
        parent_role = (
            SubagentRole.MAIN
            if params.parent_depth <= 0
            else resolve_subagent_role(params.parent_depth)
        )
        if not can_spawn_subagents(parent_role, params.parent_depth):
            return SpawnSubagentResult(
                status="forbidden",
                role=parent_role.value,
                error=(
                    f"Subagent spawn depth limit ({DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH}) reached."
                    if params.parent_depth >= DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH
                    else "Leaf subagents cannot spawn child sessions."
                ),
            )

        # 3. Validate optional task name alias
        normalized_name, err = normalize_task_name(params.task_name)
        if err:
            return SpawnSubagentResult(status="error", error=err)

        # 4. Allocate child identity
        run_id = str(uuid.uuid4())
        agent_id = params.agent_id or "subagent"
        child_session_key = f"agent:{agent_id}:subagent:{run_id}"
        child_depth = params.parent_depth + 1
        child_role = resolve_subagent_role(child_depth)
        task_id = normalized_name or f"task_{run_id[:8]}"

        # 5. Build run record
        record = SubagentRunRecord(
            run_id=run_id,
            child_session_key=child_session_key,
            parent_session_key=params.parent_session_key,
            task=params.task.strip(),
            label=params.label.strip() if params.label else (params.task[:40] + "..."),
            task_id=task_id,
            role=child_role,
            depth=child_depth,
            status=SubagentStatus.QUEUED,
            model=params.model,
            timeout_seconds=params.run_timeout_seconds,
            context_mode=params.context,
            metadata={
                "cwd": params.cwd,
                "expects_completion_message": params.expects_completion_message,
                "attachments": params.attachments or [],
            },
        )

        # 6. Register in registry
        self.registry.register_run(record)

        # 7. Launch execution task if runner factory provided
        if runner_factory:
            from .capabilities import filter_tools_for_subagent

            base_tools: dict[str, Any] = {}
            if self.tool_provider:
                base_tools = self.tool_provider(child_role)
            scoped_tools = filter_tools_for_subagent(child_role, base_tools)

            task_obj = asyncio.create_task(
                self._run_wrapper(record, runner_factory, scoped_tools),
                name=f"subagent_{run_id[:8]}",
            )
            self._active_tasks[run_id] = task_obj

        return SpawnSubagentResult(
            status="accepted",
            child_session_key=child_session_key,
            run_id=run_id,
            task_id=task_id,
            role=child_role.value,
            context=params.context.value,
        )

    async def _run_wrapper(
        self,
        record: SubagentRunRecord,
        runner_factory: Callable[[SubagentRunRecord, dict[str, Any]], Coroutine[Any, Any, None]],
        scoped_tools: dict[str, Any],
    ) -> None:
        """Internal execution wrapper with error tracking and lifecycle status updates."""
        try:
            self.registry.update_run_status(record.run_id, SubagentStatus.RUNNING)
            await asyncio.wait_for(
                runner_factory(record, scoped_tools),
                timeout=record.timeout_seconds if record.timeout_seconds > 0 else None,
            )
        except asyncio.TimeoutError:
            self.registry.update_run_status(
                record.run_id,
                SubagentStatus.TIMED_OUT,
                error=f"Subagent execution timed out after {record.timeout_seconds}s.",
            )
        except asyncio.CancelledError:
            self.registry.update_run_status(
                record.run_id,
                SubagentStatus.CANCELLED,
                error="Subagent execution was cancelled by parent or controller.",
            )
        except Exception as exc:
            self.registry.update_run_status(
                record.run_id,
                SubagentStatus.FAILED,
                error=f"Subagent runner failed: {exc}",
            )
        finally:
            self._active_tasks.pop(record.run_id, None)
            fresh_rec = self.registry.get_run(record.run_id)
            if fresh_rec and fresh_rec.metadata.get("expects_completion_message", True):
                self._dispatch_completion(fresh_rec)

    def cancel_task(self, run_id: str) -> bool:
        """Cancel a running asyncio Task associated with a run_id."""
        task = self._active_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            return True
        return False
