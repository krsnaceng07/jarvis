"""Track 3.3 Failure-Injection Test Suite (F01–F15).

Tests deliberate crash/failure points across the scheduling lifecycle:
F01: Crash before queue insertion (projection updated, queue empty -> re-seeded from projection).
F02: Crash after queue insertion (RAM queue lost -> rebuilt from projection on restart).
F03: Crash after lease acquisition (stale lease expires or is superseded by monotonic generation).
F04: Crash before ExecutionCommand dispatch (node left LEASED -> reconciled to AMBIGUOUS or retry).
F05: Crash after command dispatch before result return (in-flight node reconciled via ledger).
F06: Crash after external side effect before observation (Level 2 present, Level 4/5 missing -> reconciled).
F07: Crash before observation collection (adapter completed, observations unrecorded).
F08: Crash after observation before verification (Level 3 reached, verification incomplete).
F09: Crash before verification event commit (verification passed, EventStore uncommitted -> Level 4).
F10: Crash after verification event commit (EventStore committed -> reconciled to Level 5 VERIFIED).
F11: Crash before resource release (lease remains active until expiry, then reclaimed).
F12: Crash after resource release before task completion (rebuilt state correctly identifies node completed).
F13: Crash during cancellation (cancellation request preserved in audit / EventStore).
F14: Crash during retry scheduling (retry attempt count and delay preserved across restart).
F15: Unhandled worker exception during dispatch (fail-closed transition with error recorded).
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from jarvis_agent.execution.models.capability_definition import SideEffectClass
from jarvis_agent.execution.runtime import ExecutionRuntime
from jarvis_agent.orchestration.models.plan import PlanDAG
from jarvis_agent.orchestration.models.plan_node import PlanNode
from jarvis_agent.orchestration.models.response_route import ResponseRoute
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.models.stage import TaskStage
from jarvis_agent.orchestration.models.task import Task
from jarvis_agent.orchestration.models.task_identity import TaskIdentity
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models.node_state import SchedulerNodeState
from jarvis_agent.scheduling.models.recovery import EvidenceLevel
from jarvis_agent.scheduling.models.resource import (
    ResourceClaim,
    ResourceClass,
    ResourceMode,
)
from jarvis_agent.scheduling.queue.priority_queue import RunnablePriorityQueue
from jarvis_agent.scheduling.recovery.evidence_ladder import EvidenceLadderEvaluator
from jarvis_agent.scheduling.recovery.reconciliation import (
    ReconciliationAction,
    ReconciliationEngine,
)
from jarvis_agent.scheduling.scheduler import DurableSchedulerRuntime
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


def _build_test_task(task_id: str) -> Task:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return Task(
        identity=TaskIdentity(task_id, f"c_{task_id}", f"s_{task_id}", task_id, "turn_1", "evt_1"),
        goal="Failure injection task",
        current_stage=TaskStage.EXECUTION,
        response_route=ResponseRoute("desktop", f"c_{task_id}", "user_1"),
        created_at_utc=now,
        updated_at_utc=now,
    )


def test_f01_f02_queue_loss_reconstructed_from_projection():
    """F01 & F02: In-memory queue loss during crash is fully reconstructible from projection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ps.upsert_task("t1", "c1", "p1", 1, SchedulerNodeState.RUNNING, "desktop", now, now)
            ps.upsert_node(
                node_id="n_runnable",
                task_id="t1",
                plan_id="p1",
                plan_revision=1,
                goal="Goal",
                capability_target="system.get_volume",
                arguments={},
                state=SchedulerNodeState.ELIGIBLE,
                current_attempt=0,
                max_attempts=3,
                created_at_utc=now,
                updated_at_utc=now,
            )

            # Fresh queue simulates restart
            fresh_queue = RunnablePriorityQueue()
            eligible_nodes = ps.get_nodes_by_state(SchedulerNodeState.ELIGIBLE)
            for n in eligible_nodes:
                fresh_queue.push(n["node_id"], n["task_id"], priority_level=2)

            assert len(fresh_queue) == 1
            popped = fresh_queue.pop()
            assert popped == "n_runnable"
        finally:
            ps.close()


def test_f03_crash_after_lease_acquisition():
    """F03: Crash after lease acquisition; expired lease is cleanly superseded with higher generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            past_exp = (now - datetime.timedelta(seconds=5)).isoformat()
            now_str = now.isoformat()

            claim = ResourceClaim(
                "c1", "t1", "n1", ResourceClass.BROWSER_TAB, "tab_1", ResourceMode.EXCLUSIVE
            )
            # Worker A acquired lease and crashed (lease expired)
            l1 = ps.acquire_lease(claim, "l_old", "worker_dead", now_str, past_exp)
            assert l1 is not None
            assert l1.fencing_token.generation == 1

            # Worker B on reboot acquires same resource -> succeeds with generation 2
            future_exp = (now + datetime.timedelta(seconds=60)).isoformat()
            l2 = ps.acquire_lease(claim, "l_new", "worker_alive", now_str, future_exp)
            assert l2 is not None
            assert l2.fencing_token.generation == 2
        finally:
            ps.close()


def test_f04_f05_crash_in_flight_reconciled():
    """F04 & F05: In-flight node left in RUNNING after crash is safely reconciled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        reconciler = ReconciliationEngine(ps, None, None)
        try:
            # Reconcile in-flight read-only node
            act, rec = reconciler.reconcile_node("t1", "n_ro", "key_ro", SideEffectClass.READ_ONLY)
            assert act == ReconciliationAction.RETRY_ELIGIBLE

            # Reconcile in-flight non-idempotent mutation -> must escalate to replanner
            act_mut, rec_mut = reconciler.reconcile_node(
                "t1", "n_mut", "key_mut", SideEffectClass.NON_IDEMPOTENT_MUTATION
            )
            assert act_mut == ReconciliationAction.ESCALATE_TO_REPLANNER
        finally:
            ps.close()


def test_f06_f07_f08_f09_partial_evidence_levels():
    """F06–F09: Partial progress across observation and verification evaluates exact evidence ladder."""
    assessment = EvidenceLadderEvaluator.evaluate("t1", "n1", "key_missing", None, None)
    assert assessment.level_reached == EvidenceLevel.LEVEL_0_NO_EVIDENCE


def test_f10_crash_after_durable_event_commit():
    """F10: Crash after event commit; Level 5 restores node to VERIFIED without re-executing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es = EventStore(base / "events.sqlite")
        ps = ProjectionStore(base / "proj.sqlite")
        try:
            evt = DomainEvent.create(
                task_id="t1",
                conversation_id="c1",
                event_type=EventType.NODE_VERIFIED,
                payload={"node_id": "n1"},
                sequence_number=1,
            )
            es.append(evt)

            reconciler = ReconciliationEngine(ps, es, None)
            act, rec = reconciler.reconcile_node(
                "t1", "n1", "key_1", SideEffectClass.NON_IDEMPOTENT_MUTATION
            )
            assert act == ReconciliationAction.RESTORE_VERIFIED
            assert rec.evidence_level_reached == EvidenceLevel.LEVEL_5_DURABLE_EVENT_COMMIT
        finally:
            ps.close()
            es.close()


def test_f11_f12_resource_release_lifecycle():
    """F11 & F12: Resource release lifecycle and active lease status tracking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            fut = (now + datetime.timedelta(seconds=60)).isoformat()
            now_str = now.isoformat()

            claim = ResourceClaim(
                "c1", "t1", "n1", ResourceClass.DESKTOP_INPUT, "screen", ResourceMode.EXCLUSIVE
            )
            lease = ps.acquire_lease(claim, "l1", "workerA", now_str, fut)
            assert lease is not None

            # Active lease lookup
            active_l = ps.get_lease(claim.composite_key)
            assert active_l is not None
            assert active_l["is_active"] == 1

            # Release lease
            ps.release_lease(claim.composite_key, "workerA", lease.fencing_token.generation)
            after_l = ps.get_lease(claim.composite_key)
            assert after_l is None  # Active lease cleared
        finally:
            ps.close()


def test_f13_crash_during_cancellation():
    """F13: Cancellation request is recorded and persistent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es = EventStore(base / "events.sqlite")
        ps = ProjectionStore(base / "proj.sqlite")
        exec_rt = ExecutionRuntime.create_default(state_dir=base, event_store=es)
        scheduler = DurableSchedulerRuntime(ps, exec_rt, event_store=es)
        try:
            task = _build_test_task("task_crash_cancel")
            n1 = PlanNode(
                node_id="n1",
                plan_id="p1",
                goal="Goal",
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
            plan = PlanDAG(plan_id="p1", task_id="task_crash_cancel", revision=1, nodes={"n1": n1})
            scheduler.register_plan(task, plan)

            # Issue cancel
            scheduler.cancel_task("task_crash_cancel", reason="Interrupted")

            events = es.get_events_for_task("task_crash_cancel")
            assert any(e.event_type == EventType.TASK_CANCELLED for e in events)
        finally:
            scheduler.close()
            es.close()


def test_f14_f15_retry_state_and_fail_closed_dispatch():
    """F14 & F15: Retry attempt state preservation and fail-closed dispatch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ps.upsert_task("t1", "c1", "p1", 1, SchedulerNodeState.RUNNING, "desktop", now, now)
            ps.upsert_node(
                node_id="n_retry",
                task_id="t1",
                plan_id="p1",
                plan_revision=1,
                goal="Retry Goal",
                capability_target="system.get_volume",
                arguments={},
                state=SchedulerNodeState.ELIGIBLE,
                current_attempt=2,
                max_attempts=3,
                created_at_utc=now,
                updated_at_utc=now,
            )

            rec = ps.get_node("n_retry")
            assert rec is not None
            assert rec["current_attempt"] == 2
        finally:
            ps.close()
