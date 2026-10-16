"""Track 3.3 Dependency DAG Engine Test Suite (S17–S24).

Validates:
S17: Zero-dependency root nodes are immediately ELIGIBLE.
S18: Linear dependency chain sequential unlocking (A -> B -> C).
S19: Diamond / Fork-join dependency synchronization (A -> (B, C) -> D).
S20: Predecessor failure blocks downstream execution and records explicit failure reason.
S21: Predecessor cancellation cascades downstream blocking.
S22: Circular dependency detection via cycle finder.
S23: Topological batch partitioning finds maximal parallel stages.
S24: Independent subtrees execute concurrently without cross-blocking.
"""

from __future__ import annotations


from jarvis_agent.orchestration.models.plan import PlanDAG
from jarvis_agent.orchestration.models.plan_node import PlanNode
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.scheduling.dag.dependency_engine import DependencyEngine
from jarvis_agent.scheduling.models.node_state import SchedulerNodeState


def _make_node(node_id: str, deps: list[str]) -> PlanNode:
    return PlanNode(
        node_id=node_id,
        plan_id="plan_test",
        goal=f"Goal for {node_id}",
        capability="system.echo",
        arguments={},
        dependencies=deps,
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


def test_s17_root_node_immediate_eligibility():
    """S17: Zero-dependency root nodes are immediately ELIGIBLE."""
    n1 = _make_node("root", [])
    plan = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"root": n1})
    states = {"root": SchedulerNodeState.PENDING}

    eval_res = DependencyEngine.evaluate_node("root", plan, states)
    assert eval_res.is_eligible
    assert DependencyEngine.get_runnable_nodes(plan, states) == ["root"]


def test_s18_linear_chain_sequential_unlocking():
    """S18: Linear chain A -> B -> C sequential unlocking."""
    nA = _make_node("A", [])
    nB = _make_node("B", ["A"])
    nC = _make_node("C", ["B"])
    plan = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"A": nA, "B": nB, "C": nC})

    states = {
        "A": SchedulerNodeState.PENDING,
        "B": SchedulerNodeState.PENDING,
        "C": SchedulerNodeState.PENDING,
    }
    # Initially only A is runnable
    assert DependencyEngine.get_runnable_nodes(plan, states) == ["A"]

    # When A is VERIFIED, B becomes eligible
    states["A"] = SchedulerNodeState.VERIFIED
    assert DependencyEngine.get_runnable_nodes(plan, states) == ["B"]

    # When B is VERIFIED, C becomes eligible
    states["B"] = SchedulerNodeState.VERIFIED
    assert DependencyEngine.get_runnable_nodes(plan, states) == ["C"]


def test_s19_diamond_fork_join_synchronization():
    """S19: Diamond A -> (B, C) -> D: D only runs when BOTH B and C are VERIFIED."""
    nA = _make_node("A", [])
    nB = _make_node("B", ["A"])
    nC = _make_node("C", ["A"])
    nD = _make_node("D", ["B", "C"])
    plan = PlanDAG(
        plan_id="p1", task_id="t1", revision=1, nodes={"A": nA, "B": nB, "C": nC, "D": nD}
    )

    states = {
        "A": SchedulerNodeState.VERIFIED,
        "B": SchedulerNodeState.RUNNING,
        "C": SchedulerNodeState.VERIFIED,
        "D": SchedulerNodeState.PENDING,
    }
    # D cannot run because B is still RUNNING
    eval_D = DependencyEngine.evaluate_node("D", plan, states)
    assert not eval_D.is_eligible
    assert "B(RUNNING)" in eval_D.blocking_reason

    # Once B is VERIFIED, D unlocks
    states["B"] = SchedulerNodeState.VERIFIED
    eval_D_after = DependencyEngine.evaluate_node("D", plan, states)
    assert eval_D_after.is_eligible
    assert DependencyEngine.get_runnable_nodes(plan, states) == ["D"]


def test_s20_predecessor_failure_blocks_downstream():
    """S20: Predecessor failure blocks downstream execution and records failure reason."""
    nA = _make_node("A", [])
    nB = _make_node("B", ["A"])
    plan = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"A": nA, "B": nB})

    states = {"A": SchedulerNodeState.FAILED, "B": SchedulerNodeState.PENDING}
    eval_B = DependencyEngine.evaluate_node("B", plan, states)
    assert not eval_B.is_eligible
    assert "Prerequisite failure: A(FAILED)" in eval_B.blocking_reason


def test_s21_predecessor_cancellation_cascade():
    """S21: Predecessor cancellation cascades downstream blocking."""
    nA = _make_node("A", [])
    nB = _make_node("B", ["A"])
    plan = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"A": nA, "B": nB})

    states = {"A": SchedulerNodeState.CANCELLED, "B": SchedulerNodeState.PENDING}
    eval_B = DependencyEngine.evaluate_node("B", plan, states)
    assert not eval_B.is_eligible
    assert "Prerequisite failure: A(CANCELLED)" in eval_B.blocking_reason


def test_s22_circular_dependency_detection():
    """S22: Circular dependency detection via cycle finder."""
    nA = _make_node("A", ["B"])
    nB = _make_node("B", ["A"])
    plan = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"A": nA, "B": nB})

    cycles = DependencyEngine.detect_cycles(plan)
    assert len(cycles) > 0
    # Cycle between A and B
    assert set(cycles[0]) == {"A", "B"}


def test_s23_topological_batch_partitioning():
    """S23: Topological batch partitioning finds maximal parallel stages."""
    nA = _make_node("A", [])
    nB1 = _make_node("B1", ["A"])
    nB2 = _make_node("B2", ["A"])
    nC = _make_node("C", ["B1", "B2"])
    plan = PlanDAG(
        plan_id="p1", task_id="t1", revision=1, nodes={"A": nA, "B1": nB1, "B2": nB2, "C": nC}
    )

    batches = DependencyEngine.get_topological_batches(plan)
    assert len(batches) == 3
    assert batches[0] == ["A"]
    assert batches[1] == ["B1", "B2"]
    assert batches[2] == ["C"]


def test_s24_independent_subtrees_concurrent_execution():
    """S24: Independent subtrees execute concurrently without cross-blocking."""
    # Tree 1: T1_A -> T1_B
    t1_a = _make_node("T1_A", [])
    t1_b = _make_node("T1_B", ["T1_A"])
    # Tree 2: T2_A -> T2_B
    t2_a = _make_node("T2_A", [])
    t2_b = _make_node("T2_B", ["T2_A"])

    plan = PlanDAG(
        plan_id="p1",
        task_id="t1",
        revision=1,
        nodes={"T1_A": t1_a, "T1_B": t1_b, "T2_A": t2_a, "T2_B": t2_b},
    )
    states = {
        "T1_A": SchedulerNodeState.PENDING,
        "T1_B": SchedulerNodeState.PENDING,
        "T2_A": SchedulerNodeState.PENDING,
        "T2_B": SchedulerNodeState.PENDING,
    }
    runnable = DependencyEngine.get_runnable_nodes(plan, states)
    # Both roots must be runnable concurrently
    assert set(runnable) == {"T1_A", "T2_A"}
