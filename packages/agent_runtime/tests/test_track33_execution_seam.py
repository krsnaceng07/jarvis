"""Track 3.3 Execution Seam Test Suite (S35–S40).

Validates:
S35: Registration of Track 3.1 PlanDAG into scheduler projection tables.
S36: Initial root eligibility resolution and priority queue seeding.
S37: Dispatching node through Track 3.2 execution runtime producing VERIFIED ExecutionResult.
S38: Downstream prerequisite unlocking upon successful execution of parent node.
S39: ResponseRoute channel return binding preservation across the seam.
S40: Task cancellation cascading through the scheduler and clearing in-memory queues.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from jarvis_agent.execution.runtime import ExecutionRuntime
from jarvis_agent.orchestration.models.plan import PlanDAG
from jarvis_agent.orchestration.models.plan_node import PlanNode
from jarvis_agent.orchestration.models.response_route import ResponseRoute
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.models.task import Task
from jarvis_agent.orchestration.models.task_identity import TaskIdentity
from jarvis_agent.orchestration.models.stage import TaskStage
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models.node_state import SchedulerNodeState
from jarvis_agent.scheduling.scheduler import DurableSchedulerRuntime
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


def _build_test_task(task_id: str, channel: str = "telegram") -> Task:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    identity = TaskIdentity(
        task_id=task_id,
        conversation_id=f"conv_{task_id}",
        session_id=f"sess_{task_id}",
        root_task_id=task_id,
        turn_id="turn_1",
        creation_event_id="evt_1",
    )
    return Task(
        identity=identity,
        goal="Test execution seam",
        current_stage=TaskStage.EXECUTION,
        response_route=ResponseRoute(channel, f"conv_{task_id}", "user_1"),
        created_at_utc=now,
        updated_at_utc=now,
    )


def _build_test_plan(task_id: str) -> PlanDAG:
    n1 = PlanNode(
        node_id="node_1",
        plan_id="plan_1",
        goal="Get volume",
        capability="system.get_volume",
        arguments={},
        dependencies=[],
        status=SchedulerNodeState.PENDING,
        risk_assessment=RiskAssessment(
            risk_class=RiskClass.READ_ONLY,
            blast_radius="LOCAL_PROJECT",
            reversibility="FULLY_REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        ),
    )
    n2 = PlanNode(
        node_id="node_2",
        plan_id="plan_1",
        goal="Get volume again",
        capability="system.get_volume",
        arguments={},
        dependencies=["node_1"],
        status=SchedulerNodeState.PENDING,
        risk_assessment=RiskAssessment(
            risk_class=RiskClass.READ_ONLY,
            blast_radius="LOCAL_PROJECT",
            reversibility="FULLY_REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        ),
    )
    return PlanDAG(
        plan_id="plan_1", task_id=task_id, revision=1, nodes={"node_1": n1, "node_2": n2}
    )


def test_s35_s36_register_plan_and_eligibility():
    """S35 & S36: Register PlanDAG and verify root eligibility in queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es = EventStore(base / "events.sqlite")
        ps = ProjectionStore(base / "proj.sqlite")
        exec_rt = ExecutionRuntime.create_default(state_dir=base, event_store=es)
        scheduler = DurableSchedulerRuntime(ps, exec_rt, event_store=es)
        try:
            task = _build_test_task("task_seam_1")
            plan = _build_test_plan("task_seam_1")

            scheduler.register_plan(task, plan)

            # Check projected nodes
            n1_rec = ps.get_node("node_1")
            assert n1_rec is not None
            assert n1_rec["state"] == "ELIGIBLE"

            n2_rec = ps.get_node("node_2")
            assert n2_rec is not None
            assert n2_rec["state"] == "PENDING"

            # Check priority queue has node_1
            assert len(scheduler.queue) == 1
        finally:
            scheduler.close()
            es.close()


def test_s37_s38_schedule_next_and_dependency_unlock():
    """S37 & S38: Schedule next node through Track 3.2 and unlock child node."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es = EventStore(base / "events.sqlite")
        ps = ProjectionStore(base / "proj.sqlite")
        exec_rt = ExecutionRuntime.create_default(state_dir=base, event_store=es)
        scheduler = DurableSchedulerRuntime(ps, exec_rt, event_store=es)
        try:
            task = _build_test_task("task_seam_2")
            plan = _build_test_plan("task_seam_2")

            scheduler.register_plan(task, plan)

            # Execute node_1
            res1 = scheduler.schedule_next(task, plan)
            assert res1 is not None
            assert res1.status.value == "VERIFIED"

            # Verify node_1 updated to VERIFIED in projection
            n1_rec = ps.get_node("node_1")
            assert n1_rec["state"] == "VERIFIED"

            # Verify node_2 has now been unlocked to ELIGIBLE
            n2_rec = ps.get_node("node_2")
            assert n2_rec["state"] == "ELIGIBLE"
            assert len(scheduler.queue) == 1

            # Execute node_2
            res2 = scheduler.schedule_next(task, plan)
            assert res2 is not None
            assert res2.status.value == "VERIFIED"

            n2_rec_final = ps.get_node("node_2")
            assert n2_rec_final["state"] == "VERIFIED"
            assert len(scheduler.queue) == 0
        finally:
            scheduler.close()
            es.close()


def test_s39_response_route_preservation():
    """S39: ResponseRoute channel return binding is preserved in projected task."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es = EventStore(base / "events.sqlite")
        ps = ProjectionStore(base / "proj.sqlite")
        exec_rt = ExecutionRuntime.create_default(state_dir=base, event_store=es)
        scheduler = DurableSchedulerRuntime(ps, exec_rt, event_store=es)
        try:
            task = _build_test_task("task_tg", channel="telegram")
            plan = _build_test_plan("task_tg")

            scheduler.register_plan(task, plan)

            task_rec = ps.get_task("task_tg")
            assert task_rec is not None
            assert task_rec["channel"] == "telegram"
        finally:
            scheduler.close()
            es.close()


def test_s40_task_cancellation_cascade():
    """S40: Task cancellation cascades through the scheduler and clears queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es = EventStore(base / "events.sqlite")
        ps = ProjectionStore(base / "proj.sqlite")
        exec_rt = ExecutionRuntime.create_default(state_dir=base, event_store=es)
        scheduler = DurableSchedulerRuntime(ps, exec_rt, event_store=es)
        try:
            task = _build_test_task("task_cancel")
            plan = _build_test_plan("task_cancel")

            scheduler.register_plan(task, plan)
            assert len(scheduler.queue) == 1

            # Cancel task
            scheduler.cancel_task("task_cancel", reason="User stopped work")
            assert len(scheduler.queue) == 0

            # All nodes must be marked CANCELLED
            nodes = ps.get_nodes_for_task("task_cancel")
            for n in nodes:
                assert n["state"] == "CANCELLED"
        finally:
            scheduler.close()
            es.close()
