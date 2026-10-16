"""Unit tests for Track 3.1 Cognitive Brain, Confidence Decoupling, and Decision Policy Gate."""

from __future__ import annotations

import hashlib
import json

from jarvis_agent.orchestration.brain import (
    BrainDecisionType,
    CognitiveBrain,
    ConfidenceEvaluator,
    DecisionPolicyGate,
)
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
)
from jarvis_agent.orchestration.planning import GoalParser
from jarvis_agent.orchestration.state import RuntimeState


def test_confidence_decoupling() -> None:
    parser = GoalParser()
    goal = parser.parse("Open YouTube and play lofi")
    conf = ConfidenceEvaluator.evaluate_epistemic_confidence(goal)
    assert 0.0 <= conf <= 1.0
    # High confidence still requires policy check
    ConfidenceEvaluator.assert_confidence_does_not_authorize(conf)


def test_decision_policy_gate_authorization() -> None:
    gate = DecisionPolicyGate()
    state = RuntimeState()

    # Case A: Read-only node authorized by default
    node_ro = PlanNode(
        node_id="n_ro",
        plan_id="p1",
        goal="Inspect directory",
        capability="fs.list",
        arguments={"path": "."},
        dependencies=[],
        status=NodeStatus.READY,
        risk_assessment=RiskAssessment.safe_read_only(),
    )
    res_ro = gate.authorize_node_execution(node_ro, state)
    assert res_ro.is_authorized is True
    assert res_ro.requires_approval is False

    # Case B: High-risk node without approval blocked
    risk_high = RiskAssessment(
        risk_class=RiskClass.HIGH,
        blast_radius="HOST_FS",
        reversibility="IRREVERSIBLE",
        data_sensitivity="INTERNAL",
        external_effect="MUTATION",
        requires_operator_approval=True,
    )
    args_high = {"cmd": "rm -rf /tmp/data"}
    node_high = PlanNode(
        node_id="n_high",
        plan_id="p1",
        goal="Remove temp data",
        capability="system.sh",
        arguments=args_high,
        dependencies=[],
        status=NodeStatus.READY,
        risk_assessment=risk_high,
    )
    res_high = gate.authorize_node_execution(node_high, state)
    assert res_high.is_authorized is False
    assert res_high.requires_approval is True

    # Case C: High-risk node with granted approval authorized
    canon_json = json.dumps(args_high, sort_keys=True, separators=(",", ":"))
    args_hash = hashlib.sha256(canon_json.encode("utf-8")).hexdigest()
    appr_granted = ApprovalRequest(
        approval_id="appr_01",
        task_id="t1",
        node_id="n_high",
        capability_target="system.sh",
        arguments_hash=args_hash,
        risk_assessment=risk_high,
        status=ApprovalStatus.GRANTED,
        requested_at_utc="2026-09-20T00:00:00Z",
        expires_at_utc="2026-09-20T00:10:00Z",
    )
    state_approved = RuntimeState(approvals={"n_high": appr_granted})
    res_approved = gate.authorize_node_execution(node_high, state_approved)
    assert res_approved.is_authorized is True

    # Case D: Argument drift post-approval invalidates authorization
    node_tampered = PlanNode(
        node_id="n_high",
        plan_id="p1",
        goal="Remove root data",
        capability="system.sh",
        arguments={"cmd": "rm -rf /"},
        dependencies=[],
        status=NodeStatus.READY,
        risk_assessment=risk_high,
    )
    res_tampered = gate.authorize_node_execution(node_tampered, state_approved)
    assert res_tampered.is_authorized is False
    assert "arguments have drifted" in res_tampered.reason


def test_cognitive_brain_decisions() -> None:
    brain = CognitiveBrain()
    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")
    identity = TaskIdentity(
        task_id="t_brain",
        conversation_id="c1",
        session_id="s1",
        root_task_id="t_brain",
        turn_id="turn_1",
        creation_event_id="e1",
    )

    # 1. Task in PLANNING -> PROPOSE_PLAN
    task_planning = Task(
        identity=identity,
        goal="Play jazz music",
        current_stage=TaskStage.PLANNING,
        response_route=route,
    )
    dec_plan = brain.decide(task_planning, RuntimeState(task=task_planning))
    assert dec_plan.decision_type == BrainDecisionType.PROPOSE_PLAN

    # 2. Task in EXECUTION with ready low-risk node -> EXECUTE_NODE (authorized)
    task_exec = Task(
        identity=identity,
        goal="Play jazz music",
        current_stage=TaskStage.EXECUTION,
        response_route=route,
    )
    n1 = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Open browser",
        capability="browser.open",
        arguments={},
        dependencies=[],
        status=NodeStatus.READY,
        risk_assessment=RiskAssessment.safe_read_only(),
    )
    plan_exec = PlanDAG(plan_id="p1", task_id="t_brain", revision=1, nodes={"n1": n1})
    state_exec = RuntimeState(task=task_exec, plan=plan_exec)

    dec_exec = brain.decide(task_exec, state_exec)
    assert dec_exec.decision_type == BrainDecisionType.EXECUTE_NODE
    assert dec_exec.is_authorized is True
    assert dec_exec.node_id == "n1"
