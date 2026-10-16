"""Unit tests for Track 3.1 Stage Machine, Transition Matrix, Detector, and Oracle."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from jarvis_agent.orchestration.models import (
    ApprovalRequest,
    ApprovalStatus,
    NodeStatus,
    PlanDAG,
    PlanNode,
    ResponseRoute,
    RiskAssessment,
    RiskClass,
    Task,
    TaskIdentity,
    TaskStage,
    UserTurn,
)
from jarvis_agent.orchestration.stage import (
    IllegalStageTransitionError,
    StageDetector,
    StageReferenceOracle,
    StageTransitionEngine,
    is_transition_legal,
    validate_transition,
)
from jarvis_agent.orchestration.state import EventStore, RuntimeState


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_stage_events.sqlite"
        store = EventStore(db_path)
        yield store
        store.close()


def test_transition_rules_matrix() -> None:
    # Legal transitions
    assert is_transition_legal(TaskStage.IDLE, TaskStage.PLANNING) is True
    assert is_transition_legal(TaskStage.PLANNING, TaskStage.EXECUTION) is True
    assert is_transition_legal(TaskStage.EXECUTION, TaskStage.WAITING_FOR_TOOL) is True
    assert is_transition_legal(TaskStage.WAITING_FOR_TOOL, TaskStage.VERIFICATION) is True
    assert is_transition_legal(TaskStage.VERIFICATION, TaskStage.COMPLETED) is True

    # Illegal transitions
    assert is_transition_legal(TaskStage.COMPLETED, TaskStage.EXECUTION) is False
    assert is_transition_legal(TaskStage.IDLE, TaskStage.COMPLETED) is False
    assert is_transition_legal(TaskStage.WAITING_FOR_APPROVAL, TaskStage.COMPLETED) is False

    # Validation errors
    validate_transition(TaskStage.PLANNING, TaskStage.EXECUTION)
    with pytest.raises(IllegalStageTransitionError, match="Illegal stage transition"):
        validate_transition(TaskStage.COMPLETED, TaskStage.PLANNING)


def test_stage_detector_precedence() -> None:
    detector = StageDetector()
    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")
    identity = TaskIdentity(
        task_id="t1",
        conversation_id="c1",
        session_id="s1",
        root_task_id="t1",
        turn_id="turn_1",
        creation_event_id="e1",
    )
    task = Task(
        identity=identity,
        goal="Test Stage",
        current_stage=TaskStage.EXECUTION,
        response_route=route,
    )

    # 1. User says "stop" -> Precedence 2 overrides plan state
    turn_cancel = UserTurn(
        turn_id="turn_stop",
        request_id="r1",
        session_id="s1",
        conversation_id="c1",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Stop now!",
        clean_text="Stop now!",
        response_route=route,
    )
    res_cancel = detector.detect_stage(task, RuntimeState(task=task), latest_turn=turn_cancel)
    assert res_cancel.detected_stage == TaskStage.CANCELLED
    assert res_cancel.precedence_level == 2

    # 2. Node in WAITING_FOR_APPROVAL -> Precedence 3
    risk_high = RiskAssessment(
        risk_class=RiskClass.HIGH,
        blast_radius="HOST_FS",
        reversibility="IRREVERSIBLE",
        data_sensitivity="CONFIDENTIAL",
        external_effect="MUTATION",
        requires_operator_approval=True,
    )
    node_appr = PlanNode(
        node_id="n_crit",
        plan_id="p1",
        goal="Dangerous step",
        capability="system.format",
        arguments={},
        dependencies=[],
        status=NodeStatus.WAITING_FOR_APPROVAL,
        risk_assessment=risk_high,
    )
    plan_appr = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n_crit": node_appr})
    approval = ApprovalRequest(
        approval_id="a1",
        task_id="t1",
        node_id="n_crit",
        capability_target="system.format",
        arguments_hash="hash",
        risk_assessment=risk_high,
        status=ApprovalStatus.PENDING,
        requested_at_utc="2026-09-20T00:00:00Z",
        expires_at_utc="2026-09-20T00:10:00Z",
    )
    state_appr = RuntimeState(task=task, plan=plan_appr, approvals={"n_crit": approval})
    res_appr = detector.detect_stage(task, state_appr)
    assert res_appr.detected_stage == TaskStage.WAITING_FOR_APPROVAL
    assert res_appr.precedence_level == 3

    # 3. Node RUNNING -> Precedence 4 (WAITING_FOR_TOOL)
    risk_low = RiskAssessment.safe_read_only()
    node_running = PlanNode(
        node_id="n_run",
        plan_id="p1",
        goal="Fetch",
        capability="fetch",
        arguments={},
        dependencies=[],
        status=NodeStatus.RUNNING,
        risk_assessment=risk_low,
    )
    plan_running = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n_run": node_running})
    res_running = detector.detect_stage(task, RuntimeState(task=task, plan=plan_running))
    assert res_running.detected_stage == TaskStage.WAITING_FOR_TOOL
    assert res_running.precedence_level == 4

    # 4. Node VERIFYING -> Precedence 5 (VERIFICATION)
    node_verifying = PlanNode(
        node_id="n_ver",
        plan_id="p1",
        goal="Verify",
        capability="check",
        arguments={},
        dependencies=[],
        status=NodeStatus.VERIFYING,
        risk_assessment=risk_low,
    )
    plan_ver = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n_ver": node_verifying})
    res_ver = detector.detect_stage(task, RuntimeState(task=task, plan=plan_ver))
    assert res_ver.detected_stage == TaskStage.VERIFICATION
    assert res_ver.precedence_level == 5


def test_stage_transition_engine(temp_store: EventStore) -> None:
    engine = StageTransitionEngine(temp_store)
    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")
    identity = TaskIdentity(
        task_id="t_trans",
        conversation_id="c1",
        session_id="s1",
        root_task_id="t_trans",
        turn_id="turn_1",
        creation_event_id="e1",
    )
    task = Task(
        identity=identity,
        goal="Transition Goal",
        current_stage=TaskStage.PLANNING,
        response_route=route,
    )
    initial_state = RuntimeState(task=task)

    # Transition PLANNING -> EXECUTION (legal)
    new_state, transition = engine.transition(
        initial_state,
        target_stage=TaskStage.EXECUTION,
        reason_codes=["PLAN_VALIDATED"],
        confidence=0.99,
    )
    assert new_state.task.current_stage == TaskStage.EXECUTION
    assert transition.previous_stage == TaskStage.PLANNING
    assert transition.new_stage == TaskStage.EXECUTION

    # Verify event recorded in EventStore
    events = temp_store.get_events_for_task("t_trans")
    assert len(events) == 1
    assert events[0].payload["new_stage"] == "EXECUTION"

    # Attempt illegal transition EXECUTION -> IDLE
    with pytest.raises(IllegalStageTransitionError):
        engine.transition(new_state, target_stage=TaskStage.IDLE, reason_codes=["ILLEGAL"])


def test_stage_reference_oracle() -> None:
    oracle = StageReferenceOracle()

    # Valid trace
    valid_trace = [
        TaskStage.IDLE,
        TaskStage.PLANNING,
        TaskStage.EXECUTION,
        TaskStage.WAITING_FOR_TOOL,
        TaskStage.VERIFICATION,
        TaskStage.COMPLETED,
    ]
    violations = oracle.verify_trace(valid_trace)
    assert violations == []

    # Invalid trace (jumping from IDLE straight to COMPLETED)
    invalid_trace = [TaskStage.IDLE, TaskStage.COMPLETED]
    violations = oracle.verify_trace(invalid_trace)
    assert len(violations) == 1
    assert "Illegal transition from IDLE to COMPLETED" in violations[0]

    # Reachability
    assert oracle.is_reachable(TaskStage.IDLE, TaskStage.COMPLETED) is True
    assert oracle.is_reachable(TaskStage.COMPLETED, TaskStage.PLANNING) is False
