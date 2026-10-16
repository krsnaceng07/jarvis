"""Unit tests for Track 3.1 Planning Engine, DAG Builder, Dependency Resolver, and Plan Validator."""

from __future__ import annotations


from jarvis_agent.orchestration.models import (
    NodeStatus,
    PlanDAG,
    PlanNode,
    RiskAssessment,
    RiskClass,
    VerificationAssertion,
    VerificationRequirement,
)
from jarvis_agent.orchestration.planning import (
    DependencyResolver,
    GoalParser,
    PlanDAGBuilder,
    PlanLimits,
    PlanValidator,
)


def test_goal_parser() -> None:
    parser = GoalParser()

    # Case A: Media goal
    g_media = parser.parse("Play lofi beats on YouTube")
    assert g_media.primary_intent == "PLAY_MEDIA"
    assert "browser.navigate" in g_media.suggested_capabilities
    assert "lofi beats" in g_media.target_entities

    # Case B: File read goal
    g_file = parser.parse("Inspect the contents of data/report.json")
    assert g_file.primary_intent == "READ_FILE"
    assert "filesystem.read" in g_file.suggested_capabilities
    assert "data/report.json" in g_file.target_entities


def test_dependency_resolver() -> None:
    risk = RiskAssessment.safe_read_only()
    n1 = PlanNode(
        node_id="n1",
        plan_id="p1",
        goal="Step 1",
        capability="c1",
        arguments={},
        dependencies=[],
        status=NodeStatus.COMPLETED,
        risk_assessment=risk,
    )
    n2 = PlanNode(
        node_id="n2",
        plan_id="p1",
        goal="Step 2",
        capability="c2",
        arguments={},
        dependencies=[],
        status=NodeStatus.COMPLETED,
        risk_assessment=risk,
    )
    n3 = PlanNode(
        node_id="n3",
        plan_id="p1",
        goal="Step 3",
        capability="c3",
        arguments={},
        dependencies=["n1", "n2"],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    plan = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n1": n1, "n2": n2, "n3": n3})

    ready = DependencyResolver.get_parallel_ready_nodes(plan)
    assert len(ready) == 1
    assert ready[0].node_id == "n3"

    depth = DependencyResolver.get_critical_path_depth(plan)
    assert depth == 2

    # Missing dependencies
    n_orphan = PlanNode(
        node_id="n_orphan",
        plan_id="p1",
        goal="Bad step",
        capability="c",
        arguments={},
        dependencies=["ghost_node"],
        status=NodeStatus.PENDING,
        risk_assessment=risk,
    )
    plan_bad = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n_orphan": n_orphan})
    missing = DependencyResolver.find_missing_dependencies(plan_bad)
    assert len(missing) == 1
    assert "ghost_node" in missing[0]


def test_plan_validator_invariants() -> None:
    limits = PlanLimits(max_nodes=5, max_depth=3)
    validator = PlanValidator(limits)

    # 1. Empty plan fails
    empty_plan = PlanDAG(plan_id="p0", task_id="t1", revision=1, nodes={})
    res_empty = validator.validate(empty_plan)
    assert res_empty.is_valid is False
    assert "zero nodes" in res_empty.errors[0]

    # 2. High-risk node with missing verification fails
    risk_high = RiskAssessment(
        risk_class=RiskClass.HIGH,
        blast_radius="HOST_FS",
        reversibility="IRREVERSIBLE",
        data_sensitivity="INTERNAL",
        external_effect="MUTATION",
        requires_operator_approval=True,
    )
    n_high_unverified = PlanNode(
        node_id="n_del",
        plan_id="p1",
        goal="Delete directory",
        capability="fs.delete",
        arguments={},
        dependencies=[],
        status=NodeStatus.PENDING,
        risk_assessment=risk_high,
        verification_requirements=[],
    )
    plan_high = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n_del": n_high_unverified})
    res_high = validator.validate(plan_high)
    assert res_high.is_valid is False
    assert any("no mandatory verification requirements" in e for e in res_high.errors)

    # 3. Valid high-risk node with verification passes
    assertion = VerificationAssertion("a1", "deleted", "EQUALS", True)
    vreq = VerificationRequirement("v1", "n_del", assertions=[assertion])
    n_high_verified = PlanNode(
        node_id="n_del",
        plan_id="p1",
        goal="Delete directory",
        capability="fs.delete",
        arguments={},
        dependencies=[],
        status=NodeStatus.PENDING,
        risk_assessment=risk_high,
        verification_requirements=[vreq],
    )
    plan_valid = PlanDAG(plan_id="p1", task_id="t1", revision=1, nodes={"n_del": n_high_verified})
    res_valid = validator.validate(plan_valid)
    assert res_valid.is_valid is True


def test_dag_builder_fluent() -> None:
    builder = PlanDAGBuilder()
    dag = (
        builder.add_node("n1", "Open browser", "browser.open")
        .add_node("n2", "Navigate to URL", "browser.navigate", dependencies=["n1"])
        .build(task_id="task_yt")
    )
    assert dag.task_id == "task_yt"
    assert len(dag.nodes) == 2
    assert dag.nodes["n2"].dependencies == ["n1"]
    assert dag.has_cycle() is False
