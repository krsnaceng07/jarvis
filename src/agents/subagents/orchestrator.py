"""src.agents.subagents.orchestrator
Multi-agent orchestrator: delegation decision-making, parallel scheduling, dependency resolution, and evidence aggregation.

Matches OpenClaw parity:
- src/agents/subagents/orchestrator.ts
- src/agents/delegation-guidance.ts
- packages/agent-core/src/agent-loop.ts
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine, Sequence

from .capabilities import DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH, can_spawn_subagents
from .completion import SubagentCompletionHandler, build_child_completion_findings
from .registry import SubagentRegistry
from .spawner import SubagentSpawner
from .types import (
    SpawnSubagentParams,
    SubagentRole,
    SubagentRunRecord,
    SubagentSpawnContextMode,
    SubagentStatus,
)


class OrchestrationMode(str, Enum):
    """Execution strategy chosen by the orchestrator."""

    DIRECT_RESPONSE = "direct_response"
    DIRECT_TOOL_EXECUTION = "direct_tool_execution"
    CREATE_SUBAGENT = "create_subagent"
    RUN_PARALLEL_SUBAGENTS = "run_parallel_subagents"


@dataclass
class SubtaskDefinition:
    """A scoped subtask for multi-agent delegation."""

    task: str
    label: str = ""
    task_name: str = ""
    depends_on: list[str] | None = None  # task_names this task depends on
    context_mode: SubagentSpawnContextMode = SubagentSpawnContextMode.ISOLATED
    timeout_seconds: float = 60.0


class MultiAgentOrchestrator:
    """Coordinates parallel and sequential subagent task execution with bounded concurrency."""

    def __init__(
        self,
        spawner: SubagentSpawner | None = None,
        registry: SubagentRegistry | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.registry = registry or SubagentRegistry.get_instance()
        self.spawner = spawner or SubagentSpawner(registry=self.registry)
        self.completion_handler = SubagentCompletionHandler()
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def evaluate_orchestration_mode(
        self,
        user_intent: str,
        active_tools: Sequence[str] | None = None,
        is_subagent: bool = False,
        current_depth: int = 0,
    ) -> OrchestrationMode:
        """Determine whether the request should be answered directly, run with tools, or delegated.

        OpenClaw delegation rule:
        - If current session is a leaf subagent (depth >= max), it must NEVER spawn further subagents.
        - Independent multi-item queries (e.g. 'compare X and Y in parallel') trigger parallel subagents.
        - Multi-step background research triggers single subagent.
        - Simple commands trigger direct tool execution.
        """
        if is_subagent or current_depth >= DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH:
            return OrchestrationMode.DIRECT_TOOL_EXECUTION

        intent_lower = user_intent.lower()

        # Check for parallel multi-part keywords
        if any(
            phrase in intent_lower
            for phrase in [
                "in parallel",
                "concurrently",
                "simultaneously",
                "both at the same time",
                "fan out",
            ]
        ) or (
            "compare" in intent_lower
            and (" and " in intent_lower or " vs " in intent_lower)
            and len(user_intent) > 30
        ):
            return OrchestrationMode.RUN_PARALLEL_SUBAGENTS

        # Delegation changes the user's visibility; require explicit asynchronous intent.
        if any(
            phrase in intent_lower
            for phrase in [
                "background task",
                "run in the background",
                "do this in background",
                "asynchronous task",
                "subagent",
                "spawn subagent",
            ]
        ):
            return OrchestrationMode.CREATE_SUBAGENT

        # Simple file/PC actions
        if any(
            intent_lower.startswith(prefix)
            for prefix in ["open ", "read ", "list ", "show ", "run ", "close ", "kill "]
        ):
            return OrchestrationMode.DIRECT_TOOL_EXECUTION

        return OrchestrationMode.DIRECT_RESPONSE

    async def execute_subtasks(
        self,
        subtasks: list[SubtaskDefinition],
        parent_session_key: str = "desktop:hud",
        parent_depth: int = 0,
        runner_factory: (
            Callable[[SubagentRunRecord, dict[str, Any]], Coroutine[Any, Any, None]] | None
        ) = None,
    ) -> tuple[list[SubagentRunRecord], str | None]:
        """Execute a list of subtasks, respecting dependencies and running independent tasks in parallel."""
        # Check if parent is allowed to spawn
        parent_role = SubagentRole.MAIN if parent_depth <= 0 else SubagentRole.ORCHESTRATOR
        if not can_spawn_subagents(parent_role, parent_depth):
            raise PermissionError(
                f"Session at depth {parent_depth} is not authorized to spawn subagents."
            )

        completed_records: dict[str, SubagentRunRecord] = {}
        pending_subtasks = list(subtasks)

        while pending_subtasks:
            # Find all subtasks whose dependencies have been satisfied
            ready: list[SubtaskDefinition] = []
            for st in pending_subtasks:
                deps = st.depends_on or []
                if all(dep in completed_records for dep in deps):
                    ready.append(st)

            if not ready:
                # Cycle or unsatisfied dependency detected
                break

            for st in ready:
                pending_subtasks.remove(st)

            # If multiple ready tasks, run them concurrently via gather
            if len(ready) == 1:
                rec = await self._run_single_subtask(
                    ready[0],
                    parent_session_key=parent_session_key,
                    parent_depth=parent_depth,
                    runner_factory=runner_factory,
                    dependency_results=completed_records,
                )
                if rec:
                    task_key = ready[0].task_name or rec.run_id
                    completed_records[task_key] = rec
            else:
                tasks_coros = [
                    self._run_single_subtask(
                        st,
                        parent_session_key=parent_session_key,
                        parent_depth=parent_depth,
                        runner_factory=runner_factory,
                        dependency_results=completed_records,
                    )
                    for st in ready
                ]
                results = await asyncio.gather(*tasks_coros, return_exceptions=True)
                for st, res in zip(ready, results):
                    if isinstance(res, SubagentRunRecord):
                        task_key = st.task_name or res.run_id
                        completed_records[task_key] = res

        all_runs = list(completed_records.values())
        findings_block = build_child_completion_findings(all_runs)
        return all_runs, findings_block

    async def _run_single_subtask(
        self,
        subtask: SubtaskDefinition,
        parent_session_key: str,
        parent_depth: int,
        runner_factory: (
            Callable[[SubagentRunRecord, dict[str, Any]], Coroutine[Any, Any, None]] | None
        ),
        dependency_results: dict[str, SubagentRunRecord],
    ) -> SubagentRunRecord | None:
        """Run a single subtask bounded by the concurrency semaphore."""
        async with self._semaphore:
            # If subtask depends on previous tasks, enrich instructions with prior findings
            enriched_task = subtask.task
            if subtask.depends_on:
                prior_texts = []
                for dep in subtask.depends_on:
                    dep_rec = dependency_results.get(dep)
                    if dep_rec and dep_rec.result_text:
                        prior_texts.append(f"[{dep} output]:\n{dep_rec.result_text}")
                if prior_texts:
                    enriched_task += "\n\nInputs from prior steps:\n" + "\n\n".join(prior_texts)

            params = SpawnSubagentParams(
                task=enriched_task,
                label=subtask.label,
                task_name=subtask.task_name,
                run_timeout_seconds=subtask.timeout_seconds,
                context=subtask.context_mode,
                parent_session_key=parent_session_key,
                parent_depth=parent_depth,
            )

            result = await self.spawner.spawn(params, runner_factory=runner_factory)
            if result.status != "accepted" or not result.run_id:
                return None

            # Wait for completion in registry
            record = self.registry.get_run(result.run_id)
            if not record:
                return None

            # Wait if active task is running
            active_task = self.spawner._active_tasks.get(result.run_id)
            if active_task:
                try:
                    await active_task
                except Exception:
                    pass

            # Fetch fresh record
            fresh_record = self.registry.get_run(result.run_id)
            if fresh_record:
                # Verify physical artifacts claimed by child
                valid, err = self.completion_handler.verify_child_artifacts(fresh_record)
                if not valid and err:
                    fresh_record = self.registry.update_run_status(
                        fresh_record.run_id,
                        SubagentStatus.FAILED,
                        error=err,
                    )
                self.completion_handler.record_completion(fresh_record or record)
            return fresh_record or record
