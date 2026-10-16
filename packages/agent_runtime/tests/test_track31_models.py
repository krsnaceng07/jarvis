"""Comprehensive unit tests for Track 3.1 Orchestration domain contracts and models."""

from __future__ import annotations

import hashlib
import json
import pytest

from jarvis_agent.orchestration.models import (
    ApprovalRequest,
    ApprovalStatus,
    Attachment,
    Conversation,
    EvidenceReference,
    ExecutionCommand,
    NodeStatus,
    ObservationRecord,
    ObservationRequirement,
    PlanDAG,
    PlanDiff,
    PlanNode,
    PlanRevision,
    ResponseRoute,
    RiskAssessment,
    RiskClass,
    StageTransition,
    Task,
    TaskIdentity,
    TaskStage,
    UserTurn,
    VerificationAssertion,
    VerificationRequirement,
    VerificationResult,
)


def test_response_route_serialization() -> None:
    route = ResponseRoute(
        channel="telegram",
        conversation_id="tg_conv_42",
        user_id="user_99",
        thread_id="thread_7",
        reply_to_message_id="msg_101",
        routing_epoch=2,
    )
    data = route.to_dict()
    assert data["channel"] == "telegram"
    assert data["conversation_id"] == "tg_conv_42"

    restored = ResponseRoute.from_dict(data)
    assert restored == route


def test_user_turn_serialization() -> None:
    route = ResponseRoute(channel="desktop", conversation_id="hud_1", user_id="local_user")
    attachment = Attachment(
        attachment_id="att_1",
        filename="report.pdf",
        media_type="application/pdf",
        size_bytes=1024,
        sha256_digest="abcdef1234567890",
    )
    turn = UserTurn(
        turn_id="turn_001",
        request_id="req_001",
        session_id="sess_001",
        conversation_id="hud_1",
        user_id="local_user",
        timestamp_utc="2026-09-19T20:00:00Z",
        raw_text="Hello JARVIS, summarize this report",
        clean_text="Hello JARVIS, summarize this report",
        response_route=route,
        attachments=[attachment],
    )
    data = turn.to_dict()
    assert data["turn_id"] == "turn_001"
    assert len(data["attachments"]) == 1

    restored = UserTurn.from_dict(data)
    assert restored.turn_id == turn.turn_id
    assert restored.response_route == route
    assert len(restored.attachments) == 1
    assert restored.attachments[0].filename == "report.pdf"


def test_task_identity_lineage() -> None:
    root_id = TaskIdentity(
        task_id="task_root",
        conversation_id="conv_1",
        session_id="sess_1",
        root_task_id="task_root",
        turn_id="turn_1",
        creation_event_id="evt_1",
    )
    assert root_id.is_root is True

    child_id = TaskIdentity(
        task_id="task_child",
        conversation_id="conv_1",
        session_id="sess_1",
        root_task_id="task_root",
        turn_id="turn_2",
        creation_event_id="evt_2",
        parent_task_id="task_root",
        generation=2,
    )
    assert child_id.is_root is False
    assert child_id.parent_task_id == "task_root"

    data = child_id.to_dict()
    restored = TaskIdentity.from_dict(data)
    assert restored == child_id


def test_task_stages() -> None:
    assert TaskStage.COMPLETED.is_terminal is True
    assert TaskStage.FAILED.is_terminal is True
    assert TaskStage.CANCELLED.is_terminal is True
    assert TaskStage.EXECUTION.is_terminal is False
    assert TaskStage.WAITING_FOR_TOOL.is_waiting is True
    assert TaskStage.WAITING_FOR_APPROVAL.is_waiting is True
    assert TaskStage.PLANNING.is_active is True
    assert TaskStage.IDLE.is_active is False


def test_stage_transition() -> None:
    transition = StageTransition(
        transition_id="trans_01",
        task_id="task_1",
        previous_stage=TaskStage.PLANNING,
        new_stage=TaskStage.EXECUTION,
        reason_codes=["PLAN_VALIDATED", "ALL_PRECONDITIONS_MET"],
        confidence=0.98,
        evidence_refs=["ev_plan_hash"],
        timestamp_utc="2026-09-19T20:00:00Z",
    )
    data = transition.to_dict()
    assert data["previous_stage"] == "PLANNING"
    assert data["new_stage"] == "EXECUTION"

    restored = StageTransition.from_dict(data)
    assert restored == transition


def test_risk_and_approval_binding() -> None:
    risk = RiskAssessment(
        risk_class=RiskClass.HIGH,
        blast_radius="HOST_FS",
        reversibility="IRREVERSIBLE",
        data_sensitivity="CONFIDENTIAL",
        external_effect="EXTERNAL_MUTATION",
        requires_operator_approval=True,
        justification="Modifying system file",
    )
    assert risk.risk_class.requires_approval_by_default is True

    args = {"filepath": "C:/Windows/test.txt", "content": "hello"}
    canonical_json = json.dumps(args, sort_keys=True, separators=(",", ":"))
    valid_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    approval = ApprovalRequest(
        approval_id="appr_002",
        task_id="task_1",
        node_id="node_1",
        capability_target="filesystem.write",
        arguments_hash=valid_hash,
        risk_assessment=risk,
        status=ApprovalStatus.PENDING,
        requested_at_utc="2026-09-19T20:00:00Z",
        expires_at_utc="2026-09-19T20:10:00Z",
    )
    assert approval.validate_arguments(args) is True
    assert approval.validate_arguments({"filepath": "C:/Windows/different.txt"}) is False

    data = approval.to_dict()
    restored = ApprovalRequest.from_dict(data)
    assert restored == approval


def test_evidence_verification() -> None:
    content = b"audit log data 2026-09-19"
    ev = EvidenceReference.create_from_content(
        evidence_id="ev_001",
        evidence_type="LOG_FILE",
        content=content,
        uri="file:///logs/audit.log",
        source_node_id="node_1",
    )
    assert ev.verify_bytes(content) is True
    assert ev.verify_bytes(b"corrupted data") is False


def test_observation_and_verification() -> None:
    obs_req = ObservationRequirement(
        requirement_id="obs_01",
        predicate_type="FILE_EXISTS",
        target="data/output.csv",
        freshness_deadline_seconds=120.0,
    )
    obs_rec = ObservationRecord(
        observation_id="rec_01",
        node_id="node_1",
        captured_at_utc="2026-09-19T20:00:00Z",
        success=True,
        raw_data={"file_size": 2048},
        evidence_ref="ev_001",
    )
    assert obs_rec.success is True
    assert ObservationRecord.from_dict(obs_rec.to_dict()) == obs_rec
    assert ObservationRequirement.from_dict(obs_req.to_dict()) == obs_req

    assertion = VerificationAssertion(
        assertion_id="assert_01",
        field_name="exit_code",
        assertion_type="EQUALS",
        expected_value=0,
    )
    v_req = VerificationRequirement(
        verification_id="vreq_01",
        node_id="node_1",
        assertions=[assertion],
        mandatory=True,
    )
    v_res = VerificationResult(
        result_id="vres_01",
        verification_id="vreq_01",
        node_id="node_1",
        passed=True,
        assertions_evaluated=1,
        assertions_passed=1,
        evidence_refs=["ev_001"],
    )
    assert v_res.passed is True
    assert VerificationRequirement.from_dict(v_req.to_dict()) == v_req
    assert VerificationResult.from_dict(v_res.to_dict()) == v_res


def test_execution_command_idempotency() -> None:
    risk = RiskAssessment.safe_read_only()
    args = {"query": "SELECT 1;"}
    cmd1 = ExecutionCommand.create(
        command_id="cmd_001",
        task_id="task_1",
        plan_id="plan_1",
        node_id="node_1",
        execution_id="exec_1",
        attempt_id=1,
        plan_revision=1,
        capability_target="database.query",
        arguments=args,
        deadline_utc="2026-09-19T21:00:00Z",
        risk_assessment=risk,
    )
    cmd2 = ExecutionCommand.create(
        command_id="cmd_002",
        task_id="task_1",
        plan_id="plan_1",
        node_id="node_1",
        execution_id="exec_1",
        attempt_id=1,
        plan_revision=1,
        capability_target="database.query",
        arguments=args,
        deadline_utc="2026-09-19T21:00:00Z",
        risk_assessment=risk,
    )
    assert cmd1.arguments_hash == cmd2.arguments_hash
    assert cmd1.idempotency_key == cmd2.idempotency_key

    restored = ExecutionCommand.from_dict(cmd1.to_dict())
    assert restored == cmd1


def test_plan_dag_topological_sort_and_cycles() -> None:
    risk = RiskAssessment.safe_read_only()
    n1 = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Fetch data",
        capability="web.fetch",
        arguments={},
        dependencies=[],
        status=NodeStatus.COMPLETED,
        risk_assessment=risk,
    )
    n2 = PlanNode(
        node_id="n2",
        plan_id="p1",
        goal="Parse data",
        capability="parser.json",
        arguments={},
        dependencies=["n1"],
        status=NodeStatus.READY,
        risk_assessment=risk,
    )
    n3 = PlanNode(
        node_id="n3",
        plan_id="p1",
        goal="Store data",
        capability="db.save",
        arguments={},
        dependencies=["n2"],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )

    dag = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n1": n1, "n2": n2, "n3": n3})
    assert dag.has_cycle() is False
    order = dag.topological_sort()
    assert order == ["n1", "n2", "n3"]

    ready = dag.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].node_id == "n2"

    n_cycle = PlanNode(
        node_id="n1_cyclic",
        plan_id="p1",
        goal="Fetch data cyclic",
        capability="web.fetch",
        arguments={},
        dependencies=["n3"],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    cyclic_dag = PlanDAG(
        plan_id="p1", task_id="t1", revision=1, nodes={"n1": n_cycle, "n2": n2, "n3": n3}
    )
    assert cyclic_dag.has_cycle() is True
    with pytest.raises(ValueError, match="Cycle or unresolved dependency"):
        cyclic_dag.topological_sort()


def test_plan_dag_hash_stability() -> None:
    risk = RiskAssessment.safe_read_only()
    n1 = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Goal 1",
        capability="c1",
        arguments={},
        dependencies=[],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    n2 = PlanNode(
        node_id="n2",
        plan_id="p1",
        goal="Goal 2",
        capability="c2",
        arguments={},
        dependencies=["n1"],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    dag1 = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n1": n1, "n2": n2})
    dag2 = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n2": n2, "n1": n1})

    assert dag1.compute_plan_hash() == dag2.compute_plan_hash()


def test_plan_revision_and_diff() -> None:
    risk = RiskAssessment.safe_read_only()
    n1 = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Goal 1",
        capability="c1",
        arguments={},
        dependencies=[],
        status=NodeStatus.COMPLETED,
        risk_assessment=risk,
    )
    diff = PlanDiff(
        previous_revision=1,
        new_revision=2,
        added_nodes=[n1],
        modified_node_ids=["n2"],
        removed_node_ids=["n0"],
        preserved_completed_node_ids=["n1"],
        reason="Replanned after transient network failure",
    )
    rev = PlanRevision(
        revision_id="rev_02",
        plan_id="p1",
        task_id="t1",
        revision=2,
        plan_hash="hash_v2",
        diff=diff,
    )
    data = rev.to_dict()
    restored = PlanRevision.from_dict(data)
    assert restored.revision == 2
    assert restored.diff is not None
    assert restored.diff.reason == "Replanned after transient network failure"


def test_task_and_conversation_containers() -> None:
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
        goal="Open YouTube",
        current_stage=TaskStage.IDLE,
        response_route=route,
    )
    # Stage progression
    task_planning = task.with_stage(TaskStage.PLANNING)
    assert task_planning.current_stage == TaskStage.PLANNING
    assert task_planning.updated_at_utc >= task.updated_at_utc

    # Plan attachment
    task_with_plan = task_planning.with_plan("p1", 1)
    assert task_with_plan.current_plan_id == "p1"
    assert task_with_plan.current_plan_revision == 1

    # Conversation container
    conv = Conversation(
        conversation_id="c1",
        session_id="s1",
        channel="desktop",
        user_id="u1",
    )
    conv_with_task = conv.with_task("t1", set_focus=True)
    assert conv_with_task.current_focus_task_id == "t1"
    assert "t1" in conv_with_task.active_task_ids

    conv_with_turn = conv_with_task.with_turn("turn_1")
    assert "turn_1" in conv_with_turn.turn_ids

    # Roundtrip serialization
    assert Task.from_dict(task_with_plan.to_dict()).goal == "Open YouTube"
    assert Conversation.from_dict(conv_with_turn.to_dict()).current_focus_task_id == "t1"
