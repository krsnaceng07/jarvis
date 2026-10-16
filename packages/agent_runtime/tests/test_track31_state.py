"""Unit tests for Track 3.1 persistent event store, state reducer, and crash recovery."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from jarvis_agent.orchestration.models import (
    NodeStatus,
    PlanDAG,
    PlanNode,
    ResponseRoute,
    RiskAssessment,
    Task,
    TaskIdentity,
    TaskStage,
    VerificationResult,
)
from jarvis_agent.orchestration.state import (
    CrashRecoveryManager,
    DomainEvent,
    EventStore,
    EventType,
    SnapshotEngine,
    reduce_events,
    reduce_state,
)


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_events.sqlite"


def test_event_store_append_and_retrieve(temp_db_path: Path) -> None:
    store = EventStore(temp_db_path)
    evt1 = DomainEvent.create(
        task_id="t1",
        conversation_id="c1",
        event_type=EventType.TASK_CREATED,
        payload={"task_id": "t1"},
        sequence_number=1,
    )
    evt2 = DomainEvent.create(
        task_id="t1",
        conversation_id="c1",
        event_type=EventType.STAGE_CHANGED,
        payload={"new_stage": "PLANNING"},
        sequence_number=2,
    )
    store.append(evt1)
    store.append(evt2)

    assert store.get_latest_sequence("t1") == 2
    events = store.get_events_for_task("t1")
    assert len(events) == 2
    assert events[0].event_type == EventType.TASK_CREATED
    assert events[1].event_type == EventType.STAGE_CHANGED

    # Test filtering after sequence
    later_events = store.get_events_for_task("t1", after_sequence=1)
    assert len(later_events) == 1
    assert later_events[0].sequence_number == 2
    store.close()


def test_pure_reducer_state_progression() -> None:
    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")
    task_id = "t1"
    identity = TaskIdentity(
        task_id=task_id,
        conversation_id="c1",
        session_id="s1",
        root_task_id=task_id,
        turn_id="turn_1",
        creation_event_id="e1",
    )
    task = Task(
        identity=identity, goal="Test Goal", current_stage=TaskStage.IDLE, response_route=route
    )

    # 1. Task created
    e1 = DomainEvent.create(
        task_id=task_id,
        conversation_id="c1",
        event_type=EventType.TASK_CREATED,
        payload={"task": task.to_dict()},
        sequence_number=1,
    )
    state1 = reduce_state(None, e1)
    assert state1.task is not None
    assert state1.task.current_stage == TaskStage.IDLE
    assert state1.applied_sequence == 1

    # 2. Stage changed to PLANNING
    e2 = DomainEvent.create(
        task_id=task_id,
        conversation_id="c1",
        event_type=EventType.STAGE_CHANGED,
        payload={"new_stage": "PLANNING"},
        sequence_number=2,
    )
    state2 = reduce_state(state1, e2)
    assert state2.task is not None
    assert state2.task.current_stage == TaskStage.PLANNING
    assert state2.applied_sequence == 2

    # 3. Plan created with 1 node
    risk = RiskAssessment.safe_read_only()
    node = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Step 1",
        capability="tool.run",
        arguments={"x": 1},
        dependencies=[],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    plan = PlanDAG(plan_id="p1", task_id=task_id, revision=1, nodes={"n1": node})
    e3 = DomainEvent.create(
        task_id=task_id,
        conversation_id="c1",
        event_type=EventType.PLAN_CREATED,
        payload={"plan": plan.to_dict()},
        sequence_number=3,
    )
    state3 = reduce_state(state2, e3)
    assert state3.plan is not None
    assert "n1" in state3.plan.nodes
    assert state3.task.current_plan_id == "p1"

    # 4. Node started
    e4 = DomainEvent.create(
        task_id=task_id,
        conversation_id="c1",
        event_type=EventType.NODE_STARTED,
        payload={"node_id": "n1", "execution_id": "exec_01"},
        sequence_number=4,
    )
    state4 = reduce_state(state3, e4)
    assert state4.plan.nodes["n1"].status == NodeStatus.RUNNING

    # 5. Node verified passed
    vres = VerificationResult(
        result_id="vres_1",
        verification_id="v1",
        node_id="n1",
        passed=True,
        assertions_evaluated=1,
        assertions_passed=1,
    )
    e5 = DomainEvent.create(
        task_id=task_id,
        conversation_id="c1",
        event_type=EventType.NODE_VERIFIED,
        payload={"node_id": "n1", "verification_result": vres.to_dict()},
        sequence_number=5,
    )
    state5 = reduce_state(state4, e5)
    assert state5.plan.nodes["n1"].status == NodeStatus.COMPLETED


def test_snapshot_engine_and_full_replay_equivalence(temp_db_path: Path) -> None:
    store = EventStore(temp_db_path)
    snapshot_engine = SnapshotEngine(temp_db_path)

    route = ResponseRoute(channel="cli", conversation_id="c1", user_id="u1")
    task_id = "t_snap"
    identity = TaskIdentity(
        task_id=task_id,
        conversation_id="c1",
        session_id="s1",
        root_task_id=task_id,
        turn_id="turn_1",
        creation_event_id="e1",
    )
    task = Task(
        identity=identity, goal="Snapshot test", current_stage=TaskStage.IDLE, response_route=route
    )

    events: list[DomainEvent] = [
        DomainEvent.create(task_id, "c1", EventType.TASK_CREATED, {"task": task.to_dict()}, 1),
        DomainEvent.create(task_id, "c1", EventType.STAGE_CHANGED, {"new_stage": "PLANNING"}, 2),
        DomainEvent.create(task_id, "c1", EventType.STAGE_CHANGED, {"new_stage": "EXECUTION"}, 3),
    ]
    store.append_batch(events)

    # Replay all events
    full_state = reduce_events(None, events)
    assert full_state.applied_sequence == 3
    assert full_state.task.current_stage == TaskStage.EXECUTION

    # Save snapshot at seq 2
    partial_state = reduce_events(None, events[:2])
    snapshot_engine.save_snapshot(partial_state)

    # Load snapshot and apply remaining events
    loaded_snap = snapshot_engine.load_snapshot(task_id)
    assert loaded_snap is not None
    assert loaded_snap.applied_sequence == 2

    remaining_events = store.get_events_for_task(
        task_id, after_sequence=loaded_snap.applied_sequence
    )
    restored_state = reduce_events(loaded_snap, remaining_events)

    assert restored_state.applied_sequence == full_state.applied_sequence
    assert restored_state.task.current_stage == full_state.task.current_stage

    store.close()
    snapshot_engine.close()


def test_crash_recovery_reconciliation(temp_db_path: Path) -> None:
    store = EventStore(temp_db_path)
    snapshot_engine = SnapshotEngine(temp_db_path)

    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")
    task_id = "t_crash"
    identity = TaskIdentity(
        task_id=task_id,
        conversation_id="c1",
        session_id="s1",
        root_task_id=task_id,
        turn_id="turn_1",
        creation_event_id="e1",
    )
    task = Task(
        identity=identity,
        goal="Crash test",
        current_stage=TaskStage.EXECUTION,
        response_route=route,
    )

    risk = RiskAssessment.safe_read_only()
    n1 = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Completed Step",
        capability="tool.run",
        arguments={},
        dependencies=[],
        status=NodeStatus.COMPLETED,
        risk_assessment=risk,
    )
    n2 = PlanNode(
        node_id="n2",
        plan_id="p1",
        goal="In-Flight Step",
        capability="tool.run",
        arguments={},
        dependencies=["n1"],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    plan = PlanDAG(plan_id="p1", task_id=task_id, revision=1, nodes={"n1": n1, "n2": n2})

    events: list[DomainEvent] = [
        DomainEvent.create(task_id, "c1", EventType.TASK_CREATED, {"task": task.to_dict()}, 1),
        DomainEvent.create(task_id, "c1", EventType.PLAN_CREATED, {"plan": plan.to_dict()}, 2),
        DomainEvent.create(
            task_id, "c1", EventType.NODE_STARTED, {"node_id": "n2", "execution_id": "e_crash"}, 3
        ),
    ]
    store.append_batch(events)

    # Simulate crash right after node n2 started (it is in RUNNING state).
    # Crash recovery manager recovers the task:
    recovery_mgr = CrashRecoveryManager(store, snapshot_engine)
    recovered_state, suspect_ids = recovery_mgr.recover_task(task_id)

    assert "n2" in suspect_ids
    assert recovered_state.plan.nodes["n2"].status == NodeStatus.AMBIGUOUS_CRASH_SUSPECT
    assert recovered_state.plan.nodes["n1"].status == NodeStatus.COMPLETED

    # Journal must have recorded AMBIGUOUS_CRASH_SUSPECTED event
    latest_events = store.get_events_for_task(task_id)
    assert latest_events[-1].event_type == EventType.AMBIGUOUS_CRASH_SUSPECTED
    assert latest_events[-1].payload["node_id"] == "n2"

    store.close()
    snapshot_engine.close()
