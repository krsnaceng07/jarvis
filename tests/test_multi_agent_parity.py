"""tests.test_multi_agent_parity
OpenClaw Multi-Agent, Subagent, Delegation, and Orchestration Parity Test Suite.

Verifies:
1. Delegation decision-making (direct, single subagent, parallel subagents, leaf restriction)
2. Subagent spawning (isolated vs fork context, unique session keys, registry persistence)
3. Depth limits and runaway recursion prevention (max depth = 3)
4. Tool capability scoping (leaf denies sessions_spawn and sessions_yield)
5. Parallel execution of independent subtasks via MultiAgentOrchestrator
6. Sequential execution with dependency pipelining
7. Sessions yield and canonical child completion findings formatting
8. Cascading cancellation and descendant cleanup without orphans
9. Truthful verification of physical child claims (detecting phantom files)
10. Built-in tool integration (sessions_spawn, sessions_yield, subagents list/cancel)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.agents.sessions.tools.subagent_tools import (
    run_sessions_spawn_tool,
    run_sessions_yield_tool,
    run_subagents_tool,
)
from src.agents.subagents import (
    DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH,
    MultiAgentOrchestrator,
    OrchestrationMode,
    SpawnSubagentParams,
    SubagentCompletionHandler,
    SubagentController,
    SubagentRegistry,
    SubagentRole,
    SubagentRunner,
    SubagentRunRecord,
    SubagentSpawnContextMode,
    SubagentSpawner,
    SubagentStatus,
    SubtaskDefinition,
    can_spawn_subagents,
    filter_tools_for_subagent,
    normalize_task_name,
    resolve_subagent_role,
)


@pytest.fixture
def clean_registry(tmp_path: Path) -> SubagentRegistry:
    """Fixture providing an isolated SQLite database registry for each test."""
    db_file = tmp_path / "test_subagent.sqlite"
    SubagentRegistry.reset_instance()
    reg = SubagentRegistry.get_instance(db_path=db_file)
    reg.clear()
    yield reg
    reg.clear()
    SubagentRegistry.reset_instance()


class TestDelegationDecisions:
    """Scenario 1: Direct response vs tool execution vs subagent vs parallel delegation."""

    def test_direct_response_for_simple_queries(self, clean_registry: SubagentRegistry):
        orch = MultiAgentOrchestrator(registry=clean_registry)
        mode = orch.evaluate_orchestration_mode("Hello JARVIS, how are you today?")
        assert mode == OrchestrationMode.DIRECT_RESPONSE

    def test_direct_tool_execution_for_single_actions(self, clean_registry: SubagentRegistry):
        orch = MultiAgentOrchestrator(registry=clean_registry)
        assert (
            orch.evaluate_orchestration_mode("read package.json")
            == OrchestrationMode.DIRECT_TOOL_EXECUTION
        )
        assert (
            orch.evaluate_orchestration_mode("open File Explorer")
            == OrchestrationMode.DIRECT_TOOL_EXECUTION
        )
        assert (
            orch.evaluate_orchestration_mode("list files in E:\\jarvis")
            == OrchestrationMode.DIRECT_TOOL_EXECUTION
        )

    def test_parallel_subagents_for_concurrent_research(self, clean_registry: SubagentRegistry):
        orch = MultiAgentOrchestrator(registry=clean_registry)
        assert (
            orch.evaluate_orchestration_mode(
                "Research React vs Vue in parallel and synthesize findings"
            )
            == OrchestrationMode.RUN_PARALLEL_SUBAGENTS
        )
        assert (
            orch.evaluate_orchestration_mode("Audit frontend and backend concurrently")
            == OrchestrationMode.RUN_PARALLEL_SUBAGENTS
        )

    def test_single_subagent_for_background_investigation(self, clean_registry: SubagentRegistry):
        orch = MultiAgentOrchestrator(registry=clean_registry)
        assert (
            orch.evaluate_orchestration_mode("Start a background task to investigate server logs")
            == OrchestrationMode.CREATE_SUBAGENT
        )
        assert (
            orch.evaluate_orchestration_mode("Run deep research on quantum computing algorithms")
            == OrchestrationMode.DIRECT_TOOL_EXECUTION
        )

    def test_leaf_subagent_never_spawns(self, clean_registry: SubagentRegistry):
        orch = MultiAgentOrchestrator(registry=clean_registry)
        # Leaf subagent or current_depth >= max_depth must force direct execution
        mode = orch.evaluate_orchestration_mode(
            "Research in parallel",
            is_subagent=True,
            current_depth=DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH,
        )
        assert mode == OrchestrationMode.DIRECT_TOOL_EXECUTION


class TestCapabilitiesAndDepth:
    """Scenarios 2, 3 & 4: Role resolution, depth limit enforcement, and tool capability scoping."""

    def test_role_resolution_across_depths(self):
        assert resolve_subagent_role(0) == SubagentRole.MAIN
        assert resolve_subagent_role(1) == SubagentRole.ORCHESTRATOR
        assert resolve_subagent_role(2) == SubagentRole.ORCHESTRATOR
        assert resolve_subagent_role(3) == SubagentRole.LEAF
        assert resolve_subagent_role(4) == SubagentRole.LEAF

    def test_can_spawn_authority(self):
        assert can_spawn_subagents(SubagentRole.MAIN, depth=0) is True
        assert can_spawn_subagents(SubagentRole.ORCHESTRATOR, depth=1) is True
        assert can_spawn_subagents(SubagentRole.ORCHESTRATOR, depth=2) is True
        assert can_spawn_subagents(SubagentRole.LEAF, depth=3) is False
        assert can_spawn_subagents(SubagentRole.LEAF, depth=4) is False

    def test_tool_scoping_leaf_denies_delegation_tools(self):
        all_tools = {
            "read": {"name": "read"},
            "write": {"name": "write"},
            "edit": {"name": "edit"},
            "exec": {"name": "exec"},
            "sessions_spawn": {"name": "sessions_spawn"},
            "sessions_yield": {"name": "sessions_yield"},
            "subagents": {"name": "subagents"},
            "shutdown": {"name": "shutdown"},
        }

        leaf_tools = filter_tools_for_subagent(SubagentRole.LEAF, all_tools)
        assert "read" in leaf_tools
        assert "write" in leaf_tools
        assert "exec" in leaf_tools
        assert "subagents" in leaf_tools
        assert "sessions_spawn" not in leaf_tools
        assert "sessions_yield" not in leaf_tools
        assert "shutdown" not in leaf_tools

        orch_tools = filter_tools_for_subagent(SubagentRole.ORCHESTRATOR, all_tools)
        assert "sessions_spawn" in orch_tools
        assert "sessions_yield" in orch_tools

    @pytest.mark.asyncio
    async def test_spawner_enforces_depth_limit(self, clean_registry: SubagentRegistry):
        spawner = SubagentSpawner(registry=clean_registry)

        # Depth 0 -> allowed (child depth = 1)
        res0 = await spawner.spawn(SpawnSubagentParams(task="Task 1", parent_depth=0))
        assert res0.status == "accepted"
        assert res0.role == "orchestrator"

        # Depth 2 -> allowed (child depth = 3, leaf)
        res2 = await spawner.spawn(SpawnSubagentParams(task="Task 3", parent_depth=2))
        assert res2.status == "accepted"
        assert res2.role == "leaf"

        # Depth 3 -> forbidden (depth limit reached)
        res3 = await spawner.spawn(SpawnSubagentParams(task="Task 4", parent_depth=3))
        assert res3.status == "forbidden"
        assert "depth limit" in (res3.error or "").lower()


class TestTaskNormalizationAndContext:
    """Scenario 5: Task alias normalization and context prompt building."""

    def test_task_name_normalization(self):
        valid, err = normalize_task_name("research_topic-1")
        assert err is None
        assert valid == "research_topic-1"

        invalid, err = normalize_task_name("123_invalid")
        assert err is not None
        assert invalid == ""

    def test_runner_context_building(self, clean_registry: SubagentRegistry):
        runner = SubagentRunner(registry=clean_registry)

        rec_isolated = SubagentRunRecord(
            run_id="run_1",
            child_session_key="agent:subagent:subagent:run_1",
            parent_session_key="desktop:hud",
            task="Inspect README",
            context_mode=SubagentSpawnContextMode.ISOLATED,
        )
        ctx_iso = runner.build_prompt_context(rec_isolated, parent_context="Parent chat history")
        assert "PARENT CONTEXT FOR CONTINUATION" not in ctx_iso
        assert "Inspect README" in ctx_iso

        rec_fork = SubagentRunRecord(
            run_id="run_2",
            child_session_key="agent:subagent:subagent:run_2",
            parent_session_key="desktop:hud",
            task="Continue step 2",
            context_mode=SubagentSpawnContextMode.FORK,
        )
        ctx_fork = runner.build_prompt_context(rec_fork, parent_context="Parent chat history")
        assert "PARENT CONTEXT FOR CONTINUATION" in ctx_fork
        assert "Parent chat history" in ctx_fork


class TestMultiAgentOrchestration:
    """Scenarios 6, 7 & 8: Parallel execution, sequential dependencies, and completion findings."""

    @pytest.mark.asyncio
    async def test_parallel_subtask_execution(self, clean_registry: SubagentRegistry):
        spawner = SubagentSpawner(registry=clean_registry)
        orch = MultiAgentOrchestrator(spawner=spawner, registry=clean_registry, max_concurrency=4)

        execution_order: list[str] = []

        async def mock_runner(record: SubagentRunRecord, tools: dict[str, Any]) -> None:
            execution_order.append(f"start_{record.label}")
            await asyncio.sleep(0.05)
            clean_registry.update_run_status(
                record.run_id,
                SubagentStatus.COMPLETED,
                result_text=f"Result for {record.label}",
            )
            execution_order.append(f"end_{record.label}")

        subtasks = [
            SubtaskDefinition(task="Analyze frontend", label="Frontend", task_name="fe"),
            SubtaskDefinition(task="Analyze backend", label="Backend", task_name="be"),
            SubtaskDefinition(task="Analyze database", label="Database", task_name="db"),
        ]

        runs, findings = await orch.execute_subtasks(
            subtasks, parent_session_key="desktop:hud", runner_factory=mock_runner
        )

        assert len(runs) == 3
        assert all(r.status == SubagentStatus.COMPLETED for r in runs)
        assert findings is not None
        assert "Frontend" in findings
        assert "Backend" in findings
        assert "Database" in findings
        assert "=== Child result ===" in findings

    @pytest.mark.asyncio
    async def test_sequential_dependent_subtasks(self, clean_registry: SubagentRegistry):
        spawner = SubagentSpawner(registry=clean_registry)
        orch = MultiAgentOrchestrator(spawner=spawner, registry=clean_registry)

        async def mock_runner(record: SubagentRunRecord, tools: dict[str, Any]) -> None:
            if "step_1" in record.task:
                clean_registry.update_run_status(
                    record.run_id,
                    SubagentStatus.COMPLETED,
                    result_text="Extracted auth tokens: [token_abc]",
                )
            elif "step_2" in record.task:
                # Step 2 should receive the inputs from step 1
                clean_registry.update_run_status(
                    record.run_id,
                    SubagentStatus.COMPLETED,
                    result_text=f"Verified token: {record.task}",
                )

        subtasks = [
            SubtaskDefinition(task="Run step_1 data extraction", label="Step 1", task_name="s1"),
            SubtaskDefinition(
                task="Run step_2 verification", label="Step 2", task_name="s2", depends_on=["s1"]
            ),
        ]

        runs, findings = await orch.execute_subtasks(subtasks, runner_factory=mock_runner)

        assert len(runs) == 2
        s2_run = next(r for r in runs if r.task_id == "s2")
        assert "Extracted auth tokens: [token_abc]" in s2_run.task


class TestTruthfulnessAndPhysicalVerification:
    """Scenario 9: Child claim verification and fake outcome detection."""

    def test_detect_phantom_file_claims(self, tmp_path: Path):
        handler = SubagentCompletionHandler()
        fake_file = str(tmp_path / "phantom_file_that_does_not_exist.txt")

        record = SubagentRunRecord(
            run_id="fake_run",
            child_session_key="agent:subagent:subagent:fake_run",
            parent_session_key="desktop:hud",
            task="Create report",
            status=SubagentStatus.COMPLETED,
            tangible_artifacts=[fake_file],
        )

        valid, err = handler.verify_child_artifacts(record)
        assert valid is False
        assert "do not exist" in (err or "")

    def test_verify_actual_physical_artifacts(self, tmp_path: Path):
        handler = SubagentCompletionHandler()
        real_file = tmp_path / "actual_report.txt"
        real_file.write_text("Real data on disk", encoding="utf-8")

        record = SubagentRunRecord(
            run_id="real_run",
            child_session_key="agent:subagent:subagent:real_run",
            parent_session_key="desktop:hud",
            task="Create real report",
            status=SubagentStatus.COMPLETED,
            tangible_artifacts=[str(real_file)],
        )

        valid, err = handler.verify_child_artifacts(record)
        assert valid is True
        assert err is None


class TestTreeControlAndCascadingCancellation:
    """Scenario 10: Introspection, cascading kill, and descendant cleanup."""

    def test_cascading_cancellation(self, clean_registry: SubagentRegistry):
        spawner = SubagentSpawner(registry=clean_registry)
        controller = SubagentController(registry=clean_registry, spawner=spawner)

        # Create root, child, grandchild
        root_rec = SubagentRunRecord(
            run_id="root_1",
            child_session_key="agent:subagent:subagent:root_1",
            parent_session_key="desktop:hud",
            task="Root job",
            status=SubagentStatus.RUNNING,
        )
        clean_registry.register_run(root_rec)

        child_rec = SubagentRunRecord(
            run_id="child_1",
            child_session_key="agent:subagent:subagent:child_1",
            parent_session_key="agent:subagent:subagent:root_1",
            task="Child job",
            status=SubagentStatus.RUNNING,
        )
        clean_registry.register_run(child_rec)

        grandchild_rec = SubagentRunRecord(
            run_id="grandchild_1",
            child_session_key="agent:subagent:subagent:grandchild_1",
            parent_session_key="agent:subagent:subagent:child_1",
            task="Grandchild job",
            status=SubagentStatus.RUNNING,
        )
        clean_registry.register_run(grandchild_rec)

        # Cancel root task
        ok, msg = controller.cancel_run("root_1", caller_session_key="desktop:hud")
        assert ok is True
        assert "2 descendant(s) cancelled" in msg

        # Verify all three are cancelled in registry
        assert clean_registry.get_run("root_1").status == SubagentStatus.CANCELLED
        assert clean_registry.get_run("child_1").status == SubagentStatus.CANCELLED
        assert clean_registry.get_run("grandchild_1").status == SubagentStatus.CANCELLED

    def test_leaf_cannot_cancel_unowned_task(self, clean_registry: SubagentRegistry):
        controller = SubagentController(registry=clean_registry)

        other_rec = SubagentRunRecord(
            run_id="other_run",
            child_session_key="agent:subagent:subagent:other_run",
            parent_session_key="desktop:hud",
            task="Other task",
            status=SubagentStatus.RUNNING,
        )
        clean_registry.register_run(other_rec)

        ok, msg = controller.cancel_run(
            "other_run",
            caller_session_key="agent:subagent:subagent:leaf_session",
            caller_role=SubagentRole.LEAF,
        )
        assert ok is False
        assert "Leaf subagents cannot cancel other sessions" in msg


class TestBuiltinToolsIntegration:
    """Scenario 11: Production tools integration (sessions_spawn, sessions_yield, subagents)."""

    @pytest.mark.asyncio
    async def test_sessions_spawn_tool_execution(self, clean_registry: SubagentRegistry):
        out = await run_sessions_spawn_tool(
            "call_1",
            {
                "task": "Perform security scan of network ports",
                "label": "Port Scan",
                "taskName": "port_scan",
                "runTimeoutSeconds": 30,
            },
        )
        assert "details" in out
        details = out["details"]
        assert details["status"] == "accepted"
        assert details["task_id"] == "port_scan"
        assert details["child_session_key"].startswith("agent:subagent:subagent:")

    @pytest.mark.asyncio
    async def test_sessions_yield_tool_execution(self):
        out = await run_sessions_yield_tool(
            "call_2",
            {
                "message": "Waiting for port_scan subagent",
                "acknowledgment": "Working on that scan in the background, sir.",
            },
        )
        assert out["details"]["status"] == "yielded"
        assert out["details"]["acknowledgment"] == "Working on that scan in the background, sir."

    @pytest.mark.asyncio
    async def test_subagents_tool_list_and_cancel(self, clean_registry: SubagentRegistry):
        # 1. Spawn a task
        spawn_res = await run_sessions_spawn_tool(
            "call_3",
            {"task": "Compile assets", "taskName": "asset_build"},
        )
        run_id = spawn_res["details"]["run_id"]

        # 2. List subagents
        list_res = await run_subagents_tool("call_4", {"action": "list"})
        assert list_res["details"]["status"] == "ok"
        assert list_res["details"]["total"] >= 1

        # 3. Cancel task
        cancel_res = await run_subagents_tool(
            "call_5",
            {"action": "cancel", "taskId": run_id},
        )
        assert cancel_res["details"]["status"] == "cancelled"


class TestLiveWiringAndDeliveryParity:
    """Scenario 12: Live wiring verification (spawner completion dispatch, CLI commands, intent guidance)."""

    @pytest.mark.asyncio
    async def test_subagent_completion_listener_delivers_findings(
        self, clean_registry: SubagentRegistry
    ):
        spawner = SubagentSpawner(registry=clean_registry)
        received_findings: list[str] = []

        def on_completion(record: SubagentRunRecord, findings: str | None) -> None:
            if findings:
                received_findings.append(findings)

        spawner.register_completion_listener(on_completion)

        async def quick_runner(rec: SubagentRunRecord, tools: dict[str, Any]) -> None:
            clean_registry.update_run_status(
                rec.run_id,
                SubagentStatus.COMPLETED,
                result_text="Background job finished with 100% precision.",
            )

        res = await spawner.spawn(
            SpawnSubagentParams(task="Autonomous background job", label="Fast Job"),
            runner_factory=quick_runner,
        )

        assert res.status == "accepted"
        # Wait for the background task to complete
        task_obj = spawner._active_tasks.get(res.run_id or "")
        if task_obj:
            await task_obj

        assert len(received_findings) == 1
        assert "Fast Job" in received_findings[0]
        assert "Background job finished with 100% precision." in received_findings[0]
        assert "=== Child result ===" in received_findings[0]

    def test_cli_subagents_list_and_cancel_commands(
        self, clean_registry: SubagentRegistry, tmp_path: Path
    ):
        import argparse

        from apps.cli.src.jarvis_cli.main import _cmd_subagents_cancel, _cmd_subagents_list

        # 1. Register a test run in the clean registry
        test_rec = SubagentRunRecord(
            run_id="cli_test_run",
            child_session_key="agent:subagent:subagent:cli_test_run",
            parent_session_key="desktop:hud",
            task="CLI task",
            label="CLI Test",
            task_id="cli_task_01",
            status=SubagentStatus.RUNNING,
        )
        clean_registry.register_run(test_rec)

        # 2. Test list command
        list_args = argparse.Namespace(recent_minutes=30)
        list_exit = _cmd_subagents_list(list_args, tmp_path)
        assert list_exit == 0

        # 3. Test cancel command
        cancel_args = argparse.Namespace(task_id="cli_task_01")
        cancel_exit = _cmd_subagents_cancel(cancel_args, tmp_path)
        assert cancel_exit == 0
        assert clean_registry.get_run("cli_test_run").status == SubagentStatus.CANCELLED
