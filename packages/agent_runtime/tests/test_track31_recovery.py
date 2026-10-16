"""Unit tests for Track 3.1 Replanner, Recovery, Loop Detection, Deadlines, and Scheduler Seam."""

from __future__ import annotations

import datetime

from jarvis_agent.orchestration.models import (
    NodeStatus,
    PlanDAG,
    PlanNode,
    ResponseRoute,
    RiskAssessment,
    Task,
    TaskIdentity,
    TaskStage,
)
from jarvis_agent.orchestration.planning import Replanner
from jarvis_agent.orchestration.recovery import (
    FailureClass,
    RecoveryLoopDetector,
    RetryManager,
    RetryPolicy,
)
from jarvis_agent.orchestration.scheduling import (
    HierarchicalDeadlineEvaluator,
    SchedulerSeam,
)


def test_replanner_preserves_completed_nodes() -> None:
    risk = RiskAssessment.safe_read_only()
    replanner = Replanner()

    # Original Plan: n1 (COMPLETED) -> n2 (FAILED) -> n3 (PENDING)
    n1 = PlanNode("n1", "p1", "Step 1", "c1", {}, [], NodeStatus.COMPLETED, risk)
    n2 = PlanNode("n2", "p1", "Step 2", "c2", {}, ["n1"], NodeStatus.FAILED, risk)
    n3 = PlanNode("n3", "p1", "Step 3", "c3", {}, ["n2"], NodeStatus.PENDING, risk)
    original_plan = PlanDAG(
        plan_id="p1", task_id="t1", revision=1, nodes={"n1": n1, "n2": n2, "n3": n3}
    )

    # Substitute node for failed n2
    n2_sub = PlanNode(
        "n2_sub", "p1", "Alternative Step 2", "c2_alt", {}, ["n1"], NodeStatus.PENDING, risk
    )

    new_plan, diff, revision = replanner.replan(
        original_plan,
        failed_node_id="n2",
        reason="Network timeout on c2",
        substitute_nodes=[n2_sub],
    )

    assert new_plan.revision == 2
    assert "n1" in new_plan.nodes
    assert new_plan.nodes["n1"].status == NodeStatus.COMPLETED  # Preserved!
    assert "n2_sub" in new_plan.nodes
    assert "n2" not in new_plan.nodes  # Replaced
    assert new_plan.nodes["n3"].dependencies == ["n2_sub"]  # Re-wired downstream dependency!
    assert "n1" in diff.preserved_completed_node_ids
    assert revision.revision == 2


def test_deadline_evaluator() -> None:
    route = ResponseRoute("desktop", "c1", "u1")
    identity = TaskIdentity("t1", "c1", "s1", "t1", "turn_1", "e1")
    now = datetime.datetime.now(datetime.timezone.utc)
    old_time = (now - datetime.timedelta(seconds=4000)).isoformat()

    task_expired = Task(identity, "Goal", TaskStage.EXECUTION, route, created_at_utc=old_time)
    assert (
        HierarchicalDeadlineEvaluator.is_task_expired(
            task_expired, limit_seconds=3600.0, current_time=now
        )
        is True
    )

    # Node timeout
    risk = RiskAssessment.safe_read_only()
    node_running = PlanNode(
        "n1",
        "p1",
        "Goal",
        "c1",
        {},
        [],
        NodeStatus.RUNNING,
        risk,
        timeout_seconds=30.0,
        started_at_utc=old_time,
    )
    assert HierarchicalDeadlineEvaluator.is_node_expired(node_running, current_time=now) is True


def test_retry_manager() -> None:
    mgr = RetryManager(
        RetryPolicy(
            initial_backoff_seconds=1.0, backoff_multiplier=2.0, max_retries=3, jitter=False
        )
    )

    # Transient error is retryable
    can_retry_1, delay_1 = mgr.evaluate_retry(FailureClass.TRANSIENT, current_attempt=1)
    assert can_retry_1 is True
    assert delay_1 == 1.0

    can_retry_2, delay_2 = mgr.evaluate_retry(FailureClass.TRANSIENT, current_attempt=2)
    assert can_retry_2 is True
    assert delay_2 == 2.0

    # Exceeding retries
    can_retry_3, _ = mgr.evaluate_retry(FailureClass.TRANSIENT, current_attempt=3)
    assert can_retry_3 is False

    # Permission denied is non-retryable
    can_retry_perm, _ = mgr.evaluate_retry(FailureClass.PERMISSION_DENIED, current_attempt=1)
    assert can_retry_perm is False


def test_recovery_loop_detector() -> None:
    detector = RecoveryLoopDetector(max_occurrences=3)
    args = {"param": "value"}

    # Occurrence 1 & 2 -> no loop
    res1 = detector.record_and_check("node_fail", args, FailureClass.TRANSIENT)
    assert res1.is_loop is False
    assert res1.occurrences == 1

    res2 = detector.record_and_check("node_fail", args, FailureClass.TRANSIENT)
    assert res2.is_loop is False
    assert res2.occurrences == 2

    # Occurrence 3 -> loop detected!
    res3 = detector.record_and_check("node_fail", args, FailureClass.TRANSIENT)
    assert res3.is_loop is True
    assert res3.occurrences == 3


def test_scheduler_seam_emission() -> None:
    route = ResponseRoute("desktop", "c1", "u1")
    identity = TaskIdentity("t1", "c1", "s1", "t1", "turn_1", "e1")
    task = Task(identity, "Goal", TaskStage.EXECUTION, route)

    risk = RiskAssessment.safe_read_only()
    node = PlanNode(
        "n1", "p1", "Run query", "db.query", {"sql": "SELECT 1"}, [], NodeStatus.READY, risk
    )

    cmd = SchedulerSeam.create_command(task, plan_id="p1", plan_revision=1, node=node)
    assert cmd.task_id == "t1"
    assert cmd.node_id == "n1"
    assert cmd.attempt_id == 1
    assert cmd.idempotency_key != ""
    assert cmd.arguments_hash != ""
