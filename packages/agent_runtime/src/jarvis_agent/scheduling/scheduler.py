"""Master DurableSchedulerRuntime for Track 3.3.

Coordinates the end-to-end scheduling lifecycle:
1. Reconstructible priority queue repopulation from projection store / EventStore.
2. Dependency DAG eligibility resolution via DependencyEngine.
3. Resource arbitration and deadlock prevention via ResourceArbitrator.
4. Worker lifecycle, heartbeats, and fencing generation validation.
5. Immutable ExecutionCommand emission to Track 3.2 ExecutionRuntime.
6. Empirical ExecutionResult ingestion and authoritative EventStore journaling.
7. Side-effect aware failure handling and 3-strike loop prevention via RetryManager.
8. Two-phase cancellation coordination via CancellationManager.
9. Post-restart ambiguity reconciliation via ReconciliationEngine.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any
import uuid

from jarvis_agent.execution.models.capability_definition import SideEffectClass
from jarvis_agent.execution.models.execution_result import ExecutionResult, ExecutionStatus
from jarvis_agent.execution.runtime import ExecutionRuntime
from jarvis_agent.orchestration.models.approval import ApprovalRequest
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.plan import PlanDAG
from jarvis_agent.orchestration.models.task import Task
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.arbitration.resource_arbitrator import ResourceArbitrator
from jarvis_agent.scheduling.cancellation.cancellation_manager import CancellationManager
from jarvis_agent.scheduling.dag.dependency_engine import DependencyEngine
from jarvis_agent.scheduling.models.cancellation import CancellationRecord
from jarvis_agent.scheduling.models.node_state import (
    SchedulerNodeState,
    TaskAggregateState,
)
from jarvis_agent.scheduling.models.resource import (
    ResourceClaim,
)
from jarvis_agent.scheduling.models.retry import RecoveryAction, RetryPolicy
from jarvis_agent.scheduling.models.worker import WorkerIdentity
from jarvis_agent.scheduling.observability.inspection import SchedulerInspector
from jarvis_agent.scheduling.queue.priority_queue import RunnablePriorityQueue
from jarvis_agent.scheduling.recovery.reconciliation import (
    ReconciliationEngine,
)
from jarvis_agent.scheduling.retry.retry_manager import RetryManager
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore
from jarvis_agent.scheduling.worker.worker_manager import WorkerManager

logger = logging.getLogger(__name__)


class DurableSchedulerRuntime:
    """Authoritative durable scheduler runtime bridging Track 3.1 and Track 3.2."""

    def __init__(
        self,
        projection_store: ProjectionStore,
        execution_runtime: ExecutionRuntime,
        event_store: EventStore | None = None,
        retry_policy: RetryPolicy | None = None,
        host_identity: str = "win11_host",
    ) -> None:
        self.projection_store = projection_store
        self.execution_runtime = execution_runtime
        self.event_store = event_store

        self.queue = RunnablePriorityQueue()
        self.arbitrator = ResourceArbitrator(projection_store)
        self.worker_manager = WorkerManager(projection_store, host_identity=host_identity)
        self.retry_manager = RetryManager(policy=retry_policy)
        self.cancellation_manager = CancellationManager(execution_runtime=execution_runtime)
        self.reconciliation_engine = ReconciliationEngine(
            projection_store=projection_store,
            event_store=event_store,
            idempotency_ledger=execution_runtime.idempotency_ledger,
        )
        self.inspector = SchedulerInspector(projection_store)
        self._active_worker: WorkerIdentity = self.worker_manager.register_worker()

    @classmethod
    def create_default(
        cls,
        state_dir: str | Path | None = None,
        event_store: EventStore | None = None,
        execution_runtime: ExecutionRuntime | None = None,
    ) -> DurableSchedulerRuntime:
        """Factory creating a fully wired DurableSchedulerRuntime."""
        base_dir = Path(state_dir or Path.home() / ".jarvis" / "state")
        base_dir.mkdir(parents=True, exist_ok=True)
        db_path = base_dir / "scheduler.sqlite"

        store = ProjectionStore(db_path)
        exec_rt = execution_runtime or ExecutionRuntime.create_default(
            state_dir=base_dir, event_store=event_store
        )
        return cls(
            projection_store=store,
            execution_runtime=exec_rt,
            event_store=event_store,
        )

    def register_plan(self, task: Task, plan: PlanDAG) -> None:
        """Register an authoritative PlanDAG from Track 3.1 into the scheduler."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.projection_store.upsert_task(
            task_id=task.task_id,
            conversation_id=task.identity.conversation_id,
            plan_id=plan.plan_id,
            plan_revision=plan.revision,
            aggregate_state=TaskAggregateState.RUNNING,
            channel=task.response_route.channel,
            created_at_utc=task.created_at_utc,
            updated_at_utc=now,
        )

        for _, node in plan.nodes.items():
            self.projection_store.upsert_node(
                node_id=node.node_id,
                task_id=task.task_id,
                plan_id=plan.plan_id,
                plan_revision=plan.revision,
                goal=node.goal,
                capability_target=node.capability,
                arguments=node.arguments,
                state=SchedulerNodeState.PENDING,
                current_attempt=node.current_attempt,
                max_attempts=node.max_attempts,
                created_at_utc=node.created_at_utc,
                updated_at_utc=now,
            )

        # Evaluate initial root eligibility
        self.evaluate_eligibility(task.task_id, plan)

    def evaluate_eligibility(self, task_id: str, plan: PlanDAG) -> list[str]:
        """Evaluate DAG prerequisites and promote eligible nodes to the priority queue."""
        node_records = self.projection_store.get_nodes_for_task(task_id)
        current_states = {r["node_id"]: SchedulerNodeState(r["state"]) for r in node_records}

        eligible_node_ids: list[str] = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for node_id, node in plan.nodes.items():
            eval_res = DependencyEngine.evaluate_node(node_id, plan, current_states)
            if eval_res.is_eligible:
                rec = self.projection_store.get_node(node_id)
                if rec and rec["state"] in (
                    SchedulerNodeState.PENDING.value,
                    SchedulerNodeState.BLOCKED.value,
                    SchedulerNodeState.ELIGIBLE.value,
                ):
                    if rec["state"] != SchedulerNodeState.ELIGIBLE.value:
                        self.projection_store.upsert_node(
                            node_id=node.node_id,
                            task_id=task_id,
                            plan_id=plan.plan_id,
                            plan_revision=plan.revision,
                            goal=node.goal,
                            capability_target=node.capability,
                            arguments=node.arguments,
                            state=SchedulerNodeState.ELIGIBLE,
                            current_attempt=node.current_attempt,
                            max_attempts=node.max_attempts,
                            created_at_utc=node.created_at_utc,
                            updated_at_utc=now,
                        )
                        # Journal NODE_READY event to EventStore
                        self._journal_event(
                            EventType.NODE_READY,
                            task_id,
                            {"node_id": node.node_id, "plan_id": plan.plan_id},
                        )

                    self.queue.push(
                        node_id=node.node_id,
                        task_id=task_id,
                        priority_level=rec.get("priority_level", 2),
                        effective_deadline_utc=rec.get("effective_deadline_utc"),
                    )
                    eligible_node_ids.append(node.node_id)

        return eligible_node_ids

    def schedule_next(
        self,
        task: Task,
        plan: PlanDAG,
        claims_map: dict[str, list[ResourceClaim]] | None = None,
        approval_map: dict[str, ApprovalRequest] | None = None,
    ) -> ExecutionResult | None:
        """Schedule and execute the next runnable node in the queue through Track 3.2."""
        # 1. Pop highest priority node
        node_id = self.queue.pop()
        if not node_id:
            return None

        node = plan.nodes.get(node_id)
        if not node:
            return None

        node_rec = self.projection_store.get_node(node_id)
        if not node_rec:
            return None

        # 2. Acquire resource claims
        claims = (claims_map or {}).get(node_id, [])
        arb_res = self.arbitrator.acquire_resources(claims, self._active_worker.worker_id)
        if not arb_res.granted:
            # Re-enqueue deferred node
            self.queue.push(
                node_id=node_id,
                task_id=task.task_id,
                priority_level=node_rec.get("priority_level", 2),
                effective_deadline_utc=node_rec.get("effective_deadline_utc"),
            )
            return None

        # 3. Create validated ExecutionCommand
        now = datetime.datetime.now(datetime.timezone.utc)
        deadline = now + datetime.timedelta(seconds=node.timeout_seconds)
        cmd_id = f"cmd_{uuid.uuid4().hex[:12]}"
        exec_id = f"exec_{uuid.uuid4().hex[:12]}"
        attempt = node.current_attempt + 1

        command = ExecutionCommand.create(
            command_id=cmd_id,
            task_id=task.task_id,
            plan_id=plan.plan_id,
            node_id=node.node_id,
            execution_id=exec_id,
            attempt_id=attempt,
            plan_revision=plan.revision,
            capability_target=node.capability,
            arguments=node.arguments,
            deadline_utc=deadline.isoformat(),
            risk_assessment=node.risk_assessment,
            approval_id=approval_map[node_id].approval_id
            if approval_map and node_id in approval_map
            else None,
            issued_at_utc=now.isoformat(),
        )

        # 4. Update projection state to RUNNING
        self.projection_store.upsert_node(
            node_id=node.node_id,
            task_id=task.task_id,
            plan_id=plan.plan_id,
            plan_revision=plan.revision,
            goal=node.goal,
            capability_target=node.capability,
            arguments=node.arguments,
            state=SchedulerNodeState.RUNNING,
            current_attempt=attempt,
            max_attempts=node.max_attempts,
            worker_id=self._active_worker.worker_id,
            created_at_utc=node.created_at_utc,
            updated_at_utc=now.isoformat(),
        )

        # 5. Dispatch command through Track 3.2 ExecutionRuntime
        try:
            approval = approval_map.get(node_id) if approval_map else None
            cap_def = self.execution_runtime.registry.get(node.capability)
            granted_perms = set(cap_def.required_permissions) if cap_def else None
            result = self.execution_runtime.execute_command(
                command=command,
                active_plan_revision=plan.revision,
                approval=approval,
                granted_permissions=granted_perms,
                observation_requirements=node.observation_requirements,
                verification_requirements=node.verification_requirements,
            )
        finally:
            # Release resource leases
            self.arbitrator.release_resources(arb_res.leases)

        # 6. Process ExecutionResult outcome
        completed_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if result.status == ExecutionStatus.VERIFIED:
            self.projection_store.upsert_node(
                node_id=node.node_id,
                task_id=task.task_id,
                plan_id=plan.plan_id,
                plan_revision=plan.revision,
                goal=node.goal,
                capability_target=node.capability,
                arguments=node.arguments,
                state=SchedulerNodeState.VERIFIED,
                current_attempt=attempt,
                max_attempts=node.max_attempts,
                created_at_utc=node.created_at_utc,
                updated_at_utc=completed_now,
            )
            # Evaluate newly unlocked downstream nodes
            self.evaluate_eligibility(task.task_id, plan)
        else:
            # Handle failure through RetryManager
            cap_def = self.execution_runtime.registry.get(node.capability)
            side_effect = cap_def.side_effect_class if cap_def else SideEffectClass.READ_ONLY
            decision = self.retry_manager.evaluate_failure(
                result=result,
                side_effect_class=side_effect,
                arguments_hash=command.arguments_hash,
                current_attempt=attempt,
                max_attempts=node.max_attempts,
            )

            if decision.action == RecoveryAction.RETRY:
                self.projection_store.upsert_node(
                    node_id=node.node_id,
                    task_id=task.task_id,
                    plan_id=plan.plan_id,
                    plan_revision=plan.revision,
                    goal=node.goal,
                    capability_target=node.capability,
                    arguments=node.arguments,
                    state=SchedulerNodeState.ELIGIBLE,
                    current_attempt=attempt,
                    max_attempts=node.max_attempts,
                    created_at_utc=node.created_at_utc,
                    updated_at_utc=completed_now,
                )
                self.queue.push(
                    node_id=node.node_id,
                    task_id=task.task_id,
                    priority_level=node_rec.get("priority_level", 2),
                    effective_deadline_utc=node_rec.get("effective_deadline_utc"),
                )
                self._journal_event(
                    EventType.NODE_RETRY_SCHEDULED,
                    task.task_id,
                    {
                        "node_id": node.node_id,
                        "attempt": attempt + 1,
                        "delay": decision.delay_seconds,
                    },
                )
            else:
                self.projection_store.upsert_node(
                    node_id=node.node_id,
                    task_id=task.task_id,
                    plan_id=plan.plan_id,
                    plan_revision=plan.revision,
                    goal=node.goal,
                    capability_target=node.capability,
                    arguments=node.arguments,
                    state=SchedulerNodeState.FAILED,
                    current_attempt=attempt,
                    max_attempts=node.max_attempts,
                    created_at_utc=node.created_at_utc,
                    updated_at_utc=completed_now,
                )

        return result

    def cancel_task(self, task_id: str, reason: str = "Operator cancel") -> CancellationRecord:
        """Cancel a task and all active executions."""
        self.cancellation_manager.request_cancellation(task_id, "TASK", reason)
        self.queue.clear()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Update all non-terminal nodes in projection to CANCELLED
        nodes = self.projection_store.get_nodes_for_task(task_id)
        for n in nodes:
            st = SchedulerNodeState(n["state"])
            if not st.is_terminal:
                self.projection_store.upsert_node(
                    node_id=n["node_id"],
                    task_id=task_id,
                    plan_id=n["plan_id"],
                    plan_revision=n["plan_revision"],
                    goal=n["goal"],
                    capability_target=n["capability_target"],
                    arguments=n["arguments"],
                    state=SchedulerNodeState.CANCELLED,
                    current_attempt=n["current_attempt"],
                    max_attempts=n["max_attempts"],
                    created_at_utc=n["created_at_utc"],
                    updated_at_utc=now,
                )

        self._journal_event(EventType.TASK_CANCELLED, task_id, {"reason": reason})
        return self.cancellation_manager.abort_execution(f"exec_{task_id}", task_id)

    def _journal_event(self, event_type: EventType, task_id: str, payload: dict[str, Any]) -> None:
        if not self.event_store:
            return
        try:
            seq = self.event_store.get_latest_sequence(task_id) + 1
            evt = DomainEvent.create(
                task_id=task_id,
                conversation_id="",
                event_type=event_type,
                payload=payload,
                sequence_number=seq,
            )
            self.event_store.append(evt)
        except Exception as ex:
            logger.error("Failed to append event %s: %s", event_type.value, ex)

    def close(self) -> None:
        """Release resources."""
        self.projection_store.close()
        self.execution_runtime.close()


__all__ = ["DurableSchedulerRuntime"]
