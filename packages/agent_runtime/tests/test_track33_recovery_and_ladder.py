"""Track 3.3 Recovery, Evidence Ladder, and Inspection Test Suite (S51–S60).

Validates:
S51: Evidence Level 0 evaluation when no local or remote execution records exist.
S52: Evidence Level 2 evaluation when IdempotencyLedger reports COMPLETED without verification.
S53: Evidence Level 5 evaluation when durably committed NODE_VERIFIED event exists in EventStore.
S54: Reconciliation restores node to VERIFIED when Level 5 evidence is proven.
S55: Reconciliation resets READ_ONLY ambiguous node to RETRY_ELIGIBLE safely.
S56: Reconciliation escalates NON_IDEMPOTENT_MUTATION ambiguous node to Track 3.1 replanner.
S57: Reconciliation audit log persistently records outcome and evidence level reached.
S58: Deterministic explain_block reports exact DAG blocking reasons.
S59: Deterministic explain_block reports deadline expiration reasons.
S60: Deterministic explain_block reports failure attempts and limits.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.models.capability_definition import SideEffectClass
from jarvis_agent.execution.models.idempotency_record import IdempotencyState
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models.node_state import SchedulerNodeState
from jarvis_agent.scheduling.models.recovery import EvidenceLevel
from jarvis_agent.scheduling.observability.inspection import SchedulerInspector
from jarvis_agent.scheduling.recovery.evidence_ladder import EvidenceLadderEvaluator
from jarvis_agent.scheduling.recovery.reconciliation import (
    ReconciliationAction,
    ReconciliationEngine,
)
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


def _make_cmd(task_id: str, node_id: str, key: str) -> ExecutionCommand:
    return ExecutionCommand.create(
        command_id="cmd_1",
        task_id=task_id,
        plan_id="p1",
        node_id=node_id,
        execution_id="exec_1",
        attempt_id=1,
        plan_revision=1,
        capability_target="system.echo",
        arguments={"msg": "hi"},
        deadline_utc=(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60)
        ).isoformat(),
        risk_assessment=RiskAssessment(
            risk_class=RiskClass.READ_ONLY,
            blast_radius="LOCAL_PROJECT",
            reversibility="FULLY_REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
        ),
    )


def test_s51_evidence_level_0_no_records():
    """S51: Evidence Level 0 evaluation when no records exist."""
    assessment = EvidenceLadderEvaluator.evaluate("t1", "n1", "non_existent_key", None, None)
    assert assessment.level_reached == EvidenceLevel.LEVEL_0_NO_EVIDENCE
    assert not assessment.has_durable_event


def test_s52_evidence_level_2_ledger_completed_unverified():
    """S52: Evidence Level 2 evaluation when IdempotencyLedger reports COMPLETED without verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test_ledger.sqlite"
        ledger = IdempotencyLedger(ledger_path)
        try:
            cmd = _make_cmd("t1", "n1", "key_comp_unver")
            ledger.reserve(cmd)
            ledger.record_terminal(
                cmd.idempotency_key, IdempotencyState.COMPLETED, execution_result=None
            )

            assessment = EvidenceLadderEvaluator.evaluate(
                "t1", "n1", cmd.idempotency_key, None, ledger
            )
            assert assessment.level_reached == EvidenceLevel.LEVEL_2_EXECUTION_LEDGER
            assert assessment.has_ledger_completion
            assert not assessment.has_verified_postcondition
        finally:
            ledger.close()


def test_s53_evidence_level_5_durable_event_commit():
    """S53: Evidence Level 5 evaluation when durably committed NODE_VERIFIED event exists in EventStore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        es_path = Path(tmpdir) / "test_es.sqlite"
        es = EventStore(es_path)
        try:
            evt = DomainEvent.create(
                task_id="t_evt_5",
                conversation_id="c1",
                event_type=EventType.NODE_VERIFIED,
                payload={"node_id": "node_v5", "command_id": "cmd_v5"},
                sequence_number=1,
            )
            es.append(evt)

            assessment = EvidenceLadderEvaluator.evaluate("t_evt_5", "node_v5", "key_v5", es, None)
            assert assessment.level_reached == EvidenceLevel.LEVEL_5_DURABLE_EVENT_COMMIT
            assert assessment.has_durable_event
        finally:
            es.close()


def test_s54_reconciliation_restores_verified():
    """S54: Reconciliation restores node to VERIFIED when Level 5 evidence is proven."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps_path = Path(tmpdir) / "proj.sqlite"
        es_path = Path(tmpdir) / "events.sqlite"

        ps = ProjectionStore(ps_path)
        es = EventStore(es_path)
        try:
            evt = DomainEvent.create(
                task_id="t_rec",
                conversation_id="c1",
                event_type=EventType.NODE_VERIFIED,
                payload={"node_id": "n_rec"},
                sequence_number=1,
            )
            es.append(evt)

            reconciler = ReconciliationEngine(ps, es, None)
            action, record = reconciler.reconcile_node(
                "t_rec", "n_rec", "key_rec", SideEffectClass.READ_ONLY
            )
            assert action == ReconciliationAction.RESTORE_VERIFIED
            assert record.evidence_level_reached == EvidenceLevel.LEVEL_5_DURABLE_EVENT_COMMIT
        finally:
            ps.close()
            es.close()


def test_s55_reconciliation_resets_read_only():
    """S55: Reconciliation resets READ_ONLY ambiguous node to RETRY_ELIGIBLE safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            reconciler = ReconciliationEngine(ps, None, None)
            action, record = reconciler.reconcile_node(
                "t_ro", "n_ro", "key_ro", SideEffectClass.READ_ONLY
            )
            assert action == ReconciliationAction.RETRY_ELIGIBLE
            assert "READ_ONLY" in record.unverified_reason
        finally:
            ps.close()


def test_s56_reconciliation_escalates_non_idempotent():
    """S56: Reconciliation escalates NON_IDEMPOTENT_MUTATION ambiguous node to Track 3.1 replanner."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            reconciler = ReconciliationEngine(ps, None, None)
            action, record = reconciler.reconcile_node(
                "t_mut", "n_mut", "key_mut", SideEffectClass.NON_IDEMPOTENT_MUTATION
            )
            assert action == ReconciliationAction.ESCALATE_TO_REPLANNER
            assert "Track 3.1 replanning" in record.unverified_reason
        finally:
            ps.close()


def test_s57_reconciliation_audit_persistence():
    """S57: Reconciliation audit log persistently records outcome and evidence level reached."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        try:
            reconciler = ReconciliationEngine(ps, None, None)
            reconciler.reconcile_node(
                "t_audit", "n_audit", "key_audit", SideEffectClass.EXTERNAL_TRANSACTION
            )

            cursor = ps._conn.cursor()
            cursor.execute(
                "SELECT task_id, node_id, outcome, evidence_level FROM reconciliation_audit WHERE task_id = 't_audit';"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "t_audit"
            assert row[1] == "n_audit"
            assert row[2] == "ESCALATE_TO_REPLANNER"
            assert row[3] == 0
        finally:
            ps.close()


def test_s58_explain_block_dag_prerequisites():
    """S58: Deterministic explain_block reports exact DAG blocking reasons."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        inspector = SchedulerInspector(ps)
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ps.upsert_task("t1", "c1", "p1", 1, SchedulerNodeState.PENDING, "desktop", now, now)
            ps.upsert_node(
                node_id="n_blocked",
                task_id="t1",
                plan_id="p1",
                plan_revision=1,
                goal="Blocked node",
                capability_target="sys.echo",
                arguments={},
                state=SchedulerNodeState.BLOCKED,
                current_attempt=0,
                max_attempts=3,
                created_at_utc=now,
                updated_at_utc=now,
            )

            explanation = inspector.explain_block("n_blocked")
            assert explanation.is_blocked
            assert (
                "Waiting for prerequisite DAG nodes to be VERIFIED" in explanation.blocking_reasons
            )
        finally:
            ps.close()


def test_s59_explain_block_deadline_expired():
    """S59: Deterministic explain_block reports deadline expiration reasons."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        inspector = SchedulerInspector(ps)
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            past = (now - datetime.timedelta(seconds=10)).isoformat()
            now_str = now.isoformat()

            ps.upsert_task(
                "t1", "c1", "p1", 1, SchedulerNodeState.PENDING, "desktop", now_str, now_str
            )
            ps.upsert_node(
                node_id="n_expired",
                task_id="t1",
                plan_id="p1",
                plan_revision=1,
                goal="Expired node",
                capability_target="sys.echo",
                arguments={},
                state=SchedulerNodeState.PENDING,
                current_attempt=0,
                max_attempts=3,
                effective_deadline_utc=past,
                created_at_utc=now_str,
                updated_at_utc=now_str,
            )

            explanation = inspector.explain_block("n_expired")
            assert explanation.is_blocked
            assert explanation.is_expired
            assert any("deadline expired" in r for r in explanation.blocking_reasons)
        finally:
            ps.close()


def test_s60_explain_block_failed_node():
    """S60: Deterministic explain_block reports failure attempts and limits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ps = ProjectionStore(Path(tmpdir) / "proj.sqlite")
        inspector = SchedulerInspector(ps)
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ps.upsert_task("t1", "c1", "p1", 1, SchedulerNodeState.PENDING, "desktop", now, now)
            ps.upsert_node(
                node_id="n_failed",
                task_id="t1",
                plan_id="p1",
                plan_revision=1,
                goal="Failed node",
                capability_target="sys.echo",
                arguments={},
                state=SchedulerNodeState.FAILED,
                current_attempt=3,
                max_attempts=3,
                created_at_utc=now,
                updated_at_utc=now,
            )

            explanation = inspector.explain_block("n_failed")
            assert explanation.is_blocked
            assert any("current_attempt=3/3" in r for r in explanation.blocking_reasons)
        finally:
            ps.close()
