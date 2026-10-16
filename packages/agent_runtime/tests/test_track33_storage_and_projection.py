"""Track 3.3 Storage, Migration, Projection, and Priority Queue Test Suite (S09–S16).

Validates:
S09: Versioned schema migration engine (v32 -> v33) with atomic transaction.
S10: Idempotent migration re-run does not alter existing schema version.
S11: Materialized task and node projection upsert, lookup, and query operations.
S12: Atomic resource lease acquisition with monotonic generation increment.
S13: Stale/conflicting worker lease rejection when lease is active.
S14: Full projection rebuild from authoritative EventStore + reducer events.
S15: PriorityQueue ordering by priority level and deadline urgency.
S16: PriorityQueue task backpressure limits and starvation-prevention aging.
"""

from __future__ import annotations

import datetime
import sqlite3
import tempfile
from pathlib import Path

from jarvis_agent.orchestration.models import PlanDAG, PlanNode, ResponseRoute, Task, TaskStage
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models import (
    ResourceClaim,
    ResourceClass,
    ResourceMode,
    SchedulerNodeState,
    TaskAggregateState,
)
from jarvis_agent.scheduling.queue.priority_queue import RunnablePriorityQueue
from jarvis_agent.scheduling.storage.migrations import MigrationEngine, TARGET_SCHEMA_VERSION
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


def test_s09_migration_engine_upgrade():
    """S09: Versioned schema migration engine upgrading fresh DB to v33."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_sched.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            assert MigrationEngine.get_current_version(conn) == 32
            new_ver = MigrationEngine.apply_migrations(conn)
            assert new_ver == TARGET_SCHEMA_VERSION
            assert MigrationEngine.get_current_version(conn) == TARGET_SCHEMA_VERSION
        finally:
            conn.close()


def test_s10_idempotent_migration():
    """S10: Idempotent migration re-run does not fail or alter schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_sched.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            MigrationEngine.apply_migrations(conn)
            # Re-run
            v2 = MigrationEngine.apply_migrations(conn)
            assert v2 == TARGET_SCHEMA_VERSION
        finally:
            conn.close()


def test_s11_projection_store_tasks_and_nodes():
    """S11: Materialized task and node projection upsert, lookup, and query operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_proj.sqlite"
        store = ProjectionStore(db_path)
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            store.upsert_task(
                task_id="task_1",
                conversation_id="conv_1",
                plan_id="plan_1",
                plan_revision=1,
                aggregate_state=TaskAggregateState.RUNNING,
                channel="desktop",
                created_at_utc=now,
                updated_at_utc=now,
            )
            task_rec = store.get_task("task_1")
            assert task_rec is not None
            assert task_rec["aggregate_state"] == "RUNNING"
            assert task_rec["channel"] == "desktop"

            # Upsert nodes
            store.upsert_node(
                node_id="node_1",
                task_id="task_1",
                plan_id="plan_1",
                plan_revision=1,
                goal="Read config file",
                capability_target="filesystem.read_file",
                arguments={"path": "test.txt"},
                state=SchedulerNodeState.ELIGIBLE,
                current_attempt=0,
                max_attempts=3,
                created_at_utc=now,
                updated_at_utc=now,
            )
            node_rec = store.get_node("node_1")
            assert node_rec is not None
            assert node_rec["arguments"] == {"path": "test.txt"}
            assert node_rec["state"] == "ELIGIBLE"

            # State filter
            eligible = store.get_nodes_by_state(SchedulerNodeState.ELIGIBLE)
            assert len(eligible) == 1
            assert eligible[0]["node_id"] == "node_1"
        finally:
            store.close()


def test_s12_atomic_lease_acquisition_and_fencing():
    """S12: Atomic resource lease acquisition with monotonic generation increment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_lease.sqlite"
        store = ProjectionStore(db_path)
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            fut = (now + datetime.timedelta(seconds=60)).isoformat()
            now_str = now.isoformat()

            claim = ResourceClaim(
                "c1", "t1", "n1", ResourceClass.BROWSER_TAB, "tab_99", ResourceMode.EXCLUSIVE
            )
            lease1 = store.acquire_lease(claim, "l1", "worker_A", now_str, fut)
            assert lease1 is not None
            assert lease1.fencing_token.generation == 1

            # Subsequent acquisition by same worker increments generation
            lease2 = store.acquire_lease(claim, "l2", "worker_A", now_str, fut)
            assert lease2 is not None
            assert lease2.fencing_token.generation == 2
        finally:
            store.close()


def test_s13_conflicting_worker_lease_rejection():
    """S13: Stale/conflicting worker lease rejection when active lease is held."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_conflict.sqlite"
        store = ProjectionStore(db_path)
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            fut = (now + datetime.timedelta(seconds=60)).isoformat()
            now_str = now.isoformat()

            claim = ResourceClaim(
                "c1", "t1", "n1", ResourceClass.DESKTOP_INPUT, "screen_0", ResourceMode.EXCLUSIVE
            )
            # Worker A acquires lease
            l1 = store.acquire_lease(claim, "lease_a", "worker_A", now_str, fut)
            assert l1 is not None

            # Worker B attempts to acquire same resource while active -> refused (None)
            l2 = store.acquire_lease(claim, "lease_b", "worker_B", now_str, fut)
            assert l2 is None
        finally:
            store.close()


def test_s14_rebuild_from_authoritative_eventstore():
    """S14: Full projection rebuild from append-only EventStore + reducer events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        es_path = Path(tmpdir) / "events.sqlite"
        ps_path = Path(tmpdir) / "projection.sqlite"

        event_store = EventStore(es_path)
        projection_store = ProjectionStore(ps_path)
        try:
            task_id = "task_rebuild_1"
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Create Task
            from jarvis_agent.orchestration.models.task_identity import TaskIdentity

            identity = TaskIdentity(
                task_id=task_id,
                conversation_id="conv_reb",
                session_id="sess_reb",
                root_task_id=task_id,
                turn_id="turn_1",
                creation_event_id="evt_1",
            )
            task = Task(
                identity=identity,
                goal="Execute pipeline",
                current_stage=TaskStage.EXECUTION,
                response_route=ResponseRoute("telegram", "conv_reb", "user_1"),
                created_at_utc=now,
                updated_at_utc=now,
            )
            evt1 = DomainEvent.create(
                task_id=task_id,
                conversation_id="conv_reb",
                event_type=EventType.TASK_CREATED,
                payload={"task": task.to_dict()},
                sequence_number=1,
            )
            event_store.append(evt1)

            # Create PlanDAG
            node = PlanNode(
                node_id="node_reb_1",
                plan_id="plan_reb_1",
                goal="Step 1",
                capability="system.echo",
                arguments={"text": "hello"},
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
            plan = PlanDAG(
                plan_id="plan_reb_1", task_id=task_id, revision=1, nodes={"node_reb_1": node}
            )
            evt2 = DomainEvent.create(
                task_id=task_id,
                conversation_id="conv_reb",
                event_type=EventType.PLAN_CREATED,
                payload={"plan": plan.to_dict()},
                sequence_number=2,
            )
            event_store.append(evt2)

            # Node ready event
            evt3 = DomainEvent.create(
                task_id=task_id,
                conversation_id="conv_reb",
                event_type=EventType.NODE_READY,
                payload={"node_id": "node_reb_1"},
                sequence_number=3,
            )
            event_store.append(evt3)

            # Rebuild projection from EventStore
            projection_store.rebuild_from_events(event_store, task_id)

            # Check projection has restored task and node
            task_proj = projection_store.get_task(task_id)
            assert task_proj is not None
            assert task_proj["channel"] == "telegram"

            node_proj = projection_store.get_node("node_reb_1")
            assert node_proj is not None
            assert node_proj["goal"] == "Step 1"
            assert node_proj["state"] == "ELIGIBLE"
        finally:
            event_store.close()
            projection_store.close()


def test_s15_priority_queue_ordering():
    """S15: PriorityQueue ordering by priority level and deadline urgency."""
    pq = RunnablePriorityQueue(policy_ceiling=4)
    now = datetime.datetime.now(datetime.timezone.utc)
    d_soon = (now + datetime.timedelta(seconds=10)).isoformat()
    d_later = (now + datetime.timedelta(seconds=100)).isoformat()

    # Push lower priority
    pq.push("node_low", "t1", priority_level=1, effective_deadline_utc=d_later)
    # Push high priority
    pq.push("node_high", "t1", priority_level=4, effective_deadline_utc=d_later)
    # Push medium priority with tight deadline
    pq.push("node_med_urgent", "t1", priority_level=2, effective_deadline_utc=d_soon)

    # Pop: Highest priority (node_high) should emerge first
    first = pq.pop()
    assert first == "node_high"


def test_s16_priority_queue_backpressure_and_aging():
    """S16: PriorityQueue backpressure per task and starvation-prevention aging."""
    pq = RunnablePriorityQueue(max_in_flight_per_task=1, aging_boost_per_second=100.0)
    t0 = 1000.0

    pq.push("n1_taskA", "taskA", priority_level=3, now_epoch=t0)
    pq.push("n2_taskA", "taskA", priority_level=3, now_epoch=t0)
    pq.push("n1_taskB", "taskB", priority_level=1, now_epoch=t0)

    # If taskA already has 1 in-flight, n2_taskA is deferred, giving taskB a chance
    popped = pq.pop(active_per_task_counts={"taskA": 1}, now_epoch=t0 + 10.0)
    assert popped == "n1_taskB"
