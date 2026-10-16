"""Pure functional state reducer for orchestration RuntimeState.

Guarantees:
    RuntimeState = reduce(Snapshot, Events)
No in-memory state mutation is authoritative unless reconstructed from committed events.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from jarvis_agent.orchestration.models import (
    ApprovalRequest,
    ApprovalStatus,
    NodeStatus,
    ObservationRecord,
    PlanDAG,
    PlanRevision,
    StageTransition,
    Task,
    TaskStage,
    VerificationResult,
)
from jarvis_agent.orchestration.state.event import DomainEvent, EventType


@dataclass(frozen=True, slots=True)
class RuntimeState:
    """Immutable snapshot of authoritative reduced state for an orchestration task."""

    task: Task | None = None
    plan: PlanDAG | None = None
    revisions: tuple[PlanRevision, ...] = ()
    transitions: tuple[StageTransition, ...] = ()
    observations: dict[str, ObservationRecord] = field(default_factory=dict)
    verifications: dict[str, VerificationResult] = field(default_factory=dict)
    approvals: dict[str, ApprovalRequest] = field(default_factory=dict)
    applied_sequence: int = 0
    last_event_timestamp_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict() if self.task else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "revisions": [r.to_dict() for r in self.revisions],
            "transitions": [t.to_dict() for t in self.transitions],
            "observations": {k: v.to_dict() for k, v in self.observations.items()},
            "verifications": {k: v.to_dict() for k, v in self.verifications.items()},
            "approvals": {k: v.to_dict() for k, v in self.approvals.items()},
            "applied_sequence": self.applied_sequence,
            "last_event_timestamp_utc": self.last_event_timestamp_utc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeState:
        task = Task.from_dict(data["task"]) if data.get("task") else None
        plan = PlanDAG.from_dict(data["plan"]) if data.get("plan") else None
        revisions = tuple(
            PlanRevision.from_dict(r) if isinstance(r, dict) else r
            for r in data.get("revisions", [])
        )
        transitions = tuple(
            StageTransition.from_dict(t) if isinstance(t, dict) else t
            for t in data.get("transitions", [])
        )
        observations = {
            k: ObservationRecord.from_dict(v) if isinstance(v, dict) else v
            for k, v in data.get("observations", {}).items()
        }
        verifications = {
            k: VerificationResult.from_dict(v) if isinstance(v, dict) else v
            for k, v in data.get("verifications", {}).items()
        }
        approvals = {
            k: ApprovalRequest.from_dict(v) if isinstance(v, dict) else v
            for k, v in data.get("approvals", {}).items()
        }
        return cls(
            task=task,
            plan=plan,
            revisions=revisions,
            transitions=transitions,
            observations=observations,
            verifications=verifications,
            approvals=approvals,
            applied_sequence=int(data.get("applied_sequence", 0)),
            last_event_timestamp_utc=data.get("last_event_timestamp_utc", ""),
        )


def _update_node_in_plan(plan: PlanDAG, node_id: str, **kwargs: Any) -> PlanDAG:
    """Helper to return an updated PlanDAG with one node replaced."""
    if node_id not in plan.nodes:
        return plan
    old_node = plan.nodes[node_id]
    new_node = replace(old_node, **kwargs)
    new_nodes = dict(plan.nodes)
    new_nodes[node_id] = new_node
    return replace(plan, nodes=new_nodes)


def reduce_state(current_state: RuntimeState | None, event: DomainEvent) -> RuntimeState:
    """Pure reducer taking current RuntimeState and a DomainEvent, returning new RuntimeState."""
    state = current_state or RuntimeState()
    payload = event.payload
    evt_type = event.event_type

    task = state.task
    plan = state.plan
    revisions = list(state.revisions)
    transitions = list(state.transitions)
    observations = dict(state.observations)
    verifications = dict(state.verifications)
    approvals = dict(state.approvals)

    if evt_type == EventType.TASK_CREATED:
        task = Task.from_dict(payload["task"])

    elif evt_type == EventType.STAGE_CHANGED:
        new_stage = TaskStage(payload["new_stage"])
        if task is not None:
            task = task.with_stage(new_stage)
        if "transition" in payload:
            transitions.append(StageTransition.from_dict(payload["transition"]))

    elif evt_type == EventType.PLAN_CREATED:
        plan = PlanDAG.from_dict(payload["plan"])
        if task is not None:
            task = task.with_plan(plan.plan_id, plan.revision)

    elif evt_type == EventType.PLAN_REVISED:
        plan = PlanDAG.from_dict(payload["plan"])
        if "revision" in payload:
            revisions.append(PlanRevision.from_dict(payload["revision"]))
        if task is not None:
            task = task.with_plan(plan.plan_id, plan.revision)

    elif evt_type == EventType.NODE_READY:
        node_id = payload["node_id"]
        if plan is not None:
            plan = _update_node_in_plan(plan, node_id, status=NodeStatus.READY)

    elif evt_type == EventType.NODE_STARTED:
        node_id = payload["node_id"]
        if plan is not None:
            plan = _update_node_in_plan(
                plan,
                node_id,
                status=NodeStatus.RUNNING,
                execution_id=payload.get("execution_id"),
                started_at_utc=event.timestamp_utc,
            )

    elif evt_type == EventType.NODE_OBSERVED:
        node_id = payload["node_id"]
        obs = ObservationRecord.from_dict(payload["observation"])
        observations[node_id] = obs
        if plan is not None:
            plan = _update_node_in_plan(
                plan,
                node_id,
                last_observation_ref=obs.observation_id,
                status=NodeStatus.VERIFYING,
            )

    elif evt_type == EventType.NODE_VERIFIED:
        node_id = payload["node_id"]
        vres = VerificationResult.from_dict(payload["verification_result"])
        verifications[node_id] = vres
        if plan is not None:
            new_status = NodeStatus.COMPLETED if vres.passed else NodeStatus.FAILED
            plan = _update_node_in_plan(
                plan,
                node_id,
                status=new_status,
                last_verification_ref=vres.result_id,
                completed_at_utc=event.timestamp_utc if vres.passed else None,
                error_message=vres.error_message if not vres.passed else None,
            )

    elif evt_type == EventType.NODE_FAILED:
        node_id = payload["node_id"]
        if plan is not None:
            plan = _update_node_in_plan(
                plan,
                node_id,
                status=NodeStatus.FAILED,
                error_message=payload.get("error_message"),
            )

    elif evt_type == EventType.NODE_RETRY_SCHEDULED:
        node_id = payload["node_id"]
        if plan is not None:
            node = plan.nodes.get(node_id)
            current_attempt = (node.current_attempt + 1) if node else 1
            plan = _update_node_in_plan(
                plan,
                node_id,
                status=NodeStatus.READY,
                current_attempt=current_attempt,
            )

    elif evt_type == EventType.APPROVAL_REQUESTED:
        appr = ApprovalRequest.from_dict(payload["approval"])
        approvals[appr.node_id] = appr
        if plan is not None:
            plan = _update_node_in_plan(plan, appr.node_id, status=NodeStatus.WAITING_FOR_APPROVAL)

    elif evt_type == EventType.APPROVAL_GRANTED:
        node_id = payload["node_id"]
        if node_id in approvals:
            old_appr = approvals[node_id]
            approvals[node_id] = replace(
                old_appr,
                status=ApprovalStatus.GRANTED,
                decided_at_utc=event.timestamp_utc,
                operator_id=payload.get("operator_id"),
            )
        if plan is not None:
            plan = _update_node_in_plan(plan, node_id, status=NodeStatus.READY)

    elif evt_type == EventType.APPROVAL_DENIED:
        node_id = payload["node_id"]
        if node_id in approvals:
            old_appr = approvals[node_id]
            approvals[node_id] = replace(
                old_appr,
                status=ApprovalStatus.DENIED,
                decided_at_utc=event.timestamp_utc,
                decision_reason=payload.get("decision_reason"),
            )
        if plan is not None:
            plan = _update_node_in_plan(
                plan,
                node_id,
                status=NodeStatus.FAILED,
                error_message="Operator denied execution approval",
            )

    elif evt_type == EventType.TASK_PAUSED:
        if task is not None:
            task = task.with_stage(TaskStage.PAUSED)

    elif evt_type == EventType.TASK_RESUMED:
        if task is not None:
            task = task.with_stage(TaskStage.EXECUTION)

    elif evt_type == EventType.TASK_CANCELLED:
        if task is not None:
            task = task.with_stage(TaskStage.CANCELLED)
        if plan is not None:
            # Cancel all non-completed nodes
            new_nodes = {
                nid: replace(n, status=NodeStatus.CANCELLED) if not n.status.is_terminal else n
                for nid, n in plan.nodes.items()
            }
            plan = replace(plan, nodes=new_nodes)

    elif evt_type == EventType.TASK_COMPLETED:
        if task is not None:
            task = task.with_stage(TaskStage.COMPLETED)

    elif evt_type == EventType.AMBIGUOUS_CRASH_SUSPECTED:
        node_id = payload["node_id"]
        if plan is not None:
            plan = _update_node_in_plan(plan, node_id, status=NodeStatus.AMBIGUOUS_CRASH_SUSPECT)

    return RuntimeState(
        task=task,
        plan=plan,
        revisions=tuple(revisions),
        transitions=tuple(transitions),
        observations=observations,
        verifications=verifications,
        approvals=approvals,
        applied_sequence=event.sequence_number,
        last_event_timestamp_utc=event.timestamp_utc,
    )


def reduce_events(
    initial_state: RuntimeState | None,
    events: list[DomainEvent],
) -> RuntimeState:
    """Deterministically replay a sequence of events onto an initial state."""
    state = initial_state or RuntimeState()
    for evt in events:
        state = reduce_state(state, evt)
    return state


__all__ = ["RuntimeState", "reduce_events", "reduce_state"]
