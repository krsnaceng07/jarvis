"""packages/learning_core/tests/test_wave5.py — Capstone validation test suite.

Validates Wave 5 requirements:
1. All 8 end-to-end learning scenarios pass.
2. Three-way negative controls (A: No learning, B: Memory-only, C: Full pipeline).
3. Background TrainingWorker runs detached with resource limits, pause, resume, abort.
4. EvidenceRecorder exports verified artifacts with SHA-256 checksums.
5. StrategyLineage provenance validation rejects manual contamination.
6. Learning plugin hook idempotency prevents duplicate experience recording.
7. CLI commands (status, demo) return valid JSON and enforce deterministic CI modes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from jarvis_learning.cli import handle_demo, handle_status
from jarvis_learning.demo import (
    ControlArm,
    assess_learning_effect,
    execute_turn_with_arm,
    run_scenario_1_cross_session_recovery,
    run_scenario_2_failure_avoidance,
    run_scenario_3_shadow_qualification,
    run_scenario_4_classified_rollback,
    run_scenario_5_workspace_continuity,
    run_scenario_6_persistent_reload,
    run_scenario_7_partial_task_recovery,
    run_scenario_8_truthful_reporting,
)
from jarvis_learning.engine import LearningEngine
from jarvis_learning.evidence import EvidenceRecorder
from jarvis_learning.lineage import (
    LearningEffectResult,
    StrategyLineage,
    VerificationOutcome,
    validate_strategy_provenance,
)
from jarvis_learning.worker import TrainingResourcePolicy, TrainingWorker


class TestWave5Scenarios:
    """Validate all 8 capstone learning scenarios."""

    def test_scenario_1_cross_session_tool_learning_with_restart(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_1.sqlite")
        res = run_scenario_1_cross_session_recovery(db_path)
        assert res["status"] == "passed"
        assert res["strategy_source"] == "persistent_sqlite"
        assert res["conversation_memory_match"] is False
        assert res["previous_session_context_used"] is False
        assert res["wrong_tool_repeat"] is False
        assert res["selected_tool"] == "volume.mute"
        assert res["confidence"] >= 0.85
        assert res["final_state_verified"] is True
        assert res["session_1_id"] != res["session_2_id"]

        # Test with alternative paraphrase prompt
        res_para = run_scenario_1_cross_session_recovery(
            db_path, paraphrased_prompt="Shut down all sound output completely"
        )
        assert res_para["status"] == "passed"
        assert res_para["selected_tool"] == "volume.mute"

    def test_scenario_2_scoped_failure_pattern_avoidance(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_2.sqlite")
        res = run_scenario_2_failure_avoidance(db_path)
        assert res["status"] == "passed"
        assert res["scoped_avoidance_working"] is True
        assert res["overgeneralization_prevented"] is True
        assert res["dangerous_command_executed"] is False

    def test_scenario_3_shadow_qualification_and_operator_gate(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_3.sqlite")
        res = run_scenario_3_shadow_qualification(db_path)
        assert res["status"] == "passed"
        assert res["qualified"] is True
        assert res["sample_count"] >= 20
        assert res["accuracy"] >= 0.85
        assert len(res["categories_covered"]) >= 3
        assert res["auto_promotion_blocked"] is True
        assert res["operator_approval_respected"] is True

    def test_scenario_4_classified_rollback_and_restart_persistence(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_4.sqlite")
        res = run_scenario_4_classified_rollback(db_path)
        assert res["status"] == "passed"
        assert res["rollback_triggered"] is True
        assert "consecutive model-caused failures" in res["trigger_reason"].lower()
        assert res["active_after_restart"] == "tfidf_baseline_v1"
        assert res["failed_candidate_state"] == "rolled_back"

    def test_scenario_5_workspace_state_continuity_tab_reuse(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_5.sqlite")
        res = run_scenario_5_workspace_continuity(db_path)
        assert res["status"] == "passed"
        assert res["existing_tab_reused"] is True
        assert res["duplicate_tabs_prevented"] is True
        assert res["target_id"] == "target_tab_yt_99"
        assert res["turn2_tool"] == "browser.search"
        assert res["turn3_tool"] == "browser.search"

    def test_scenario_6_persistent_memory_reload_without_regeneration(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_6.sqlite")
        res = run_scenario_6_persistent_reload(db_path)
        assert res["status"] == "passed"
        assert res["persistence_survived_restart"] is True
        assert res["strategy_id"] == "strat_persistent_p6"
        assert res["schema_verified"] is True
        assert res["in_memory_leakage"] is False

    def test_scenario_7_partial_stage_recovery(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scenario_7.sqlite")
        res = run_scenario_7_partial_task_recovery(db_path)
        assert res["status"] == "passed"
        assert res["completed_step_relaunch_prevented"] is True
        assert res["active_app_reused"] == "spotify_proc_12"
        assert res["resumed_stage"] == "app_launched"

    def test_scenario_8_truthful_reporting_and_false_completion_prevention(
        self, tmp_path: Path
    ) -> None:
        db_path = str(tmp_path / "scenario_8.sqlite")
        res = run_scenario_8_truthful_reporting(db_path)
        assert res["status"] == "passed"
        assert res["verification_outcome"] == VerificationOutcome.VERIFIED_FAILURE.value
        assert res["false_completion_prevented"] is True
        assert "state remained unchanged" in res["truthful_report"]


class TestThreeWayControls:
    """Validate 3-way negative controls (No learning vs Memory-only vs Full pipeline)."""

    def test_three_way_controls_and_effect_size(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "controls.sqlite")
        prompt = "Silence computer sound"

        arm_a = execute_turn_with_arm(ControlArm.A_NO_LEARNING, prompt, db_path=db_path)
        arm_b = execute_turn_with_arm(ControlArm.B_MEMORY_ONLY, prompt, db_path=db_path)
        arm_c = execute_turn_with_arm(ControlArm.C_FULL_PIPELINE, prompt, db_path=db_path)

        assert arm_a.arm == ControlArm.A_NO_LEARNING
        assert arm_b.arm == ControlArm.B_MEMORY_ONLY
        assert arm_c.arm == ControlArm.C_FULL_PIPELINE

        effect = assess_learning_effect(arm_a, arm_b, arm_c)
        assert effect.result == LearningEffectResult.PROVEN
        assert effect.arm_c_success is True
        assert effect.arm_a_success is False
        assert effect.effect_size > 0.0


class TestOfflineTrainingWorker:
    """Validate detached background training worker and resource caps."""

    def test_background_worker_detached_execution(self) -> None:
        policy = TrainingResourcePolicy(max_threads=2, max_memory_mb=512)
        worker = TrainingWorker(policy=policy)
        worker.start()

        completed = []

        def sample_job() -> str:
            time.sleep(0.05)
            return "done"

        job_id = worker.enqueue(
            "test_target", sample_job, callback=lambda res: completed.append(res)
        )
        assert job_id is not None
        assert worker.is_running() is True

        # Wait for job completion
        for _ in range(50):
            if completed:
                break
            time.sleep(0.02)

        assert len(completed) == 1
        assert completed[0] == "done"

        # Test pause and resume
        worker.pause()
        assert worker.is_paused() is True
        worker.resume()
        assert worker.is_paused() is False

        worker.stop()
        assert worker.is_running() is False


class TestEvidenceRecorderAndLineage:
    """Validate machine-readable evidence export, checksums, and lineage rules."""

    def test_evidence_recorder_artifacts_and_checksums(self, tmp_path: Path) -> None:
        recorder = EvidenceRecorder(output_dir=tmp_path)
        recorder.record_trace({"trace_id": "tr_001", "action": "volume.mute"})
        recorder.record_experience({"id": "exp_001", "success": True})
        recorder.record_strategy_lineage(
            {
                "strategy_id": "strat_001",
                "origin": "reflection",
                "verified": True,
                "manual_override": False,
            }
        )
        recorder.record_model_eval({"model_id": "m1", "val_accuracy": 0.92})
        recorder.record_benchmark_scorecard({"total": 18, "passed": 18, "score": 1.0})

        manifest = recorder.export_manifest(
            run_id="run_test_001",
            scenario="full_validation",
            learning_effect="proven",
        )

        assert manifest.run_id == "run_test_001"
        assert manifest.learning_effect == "proven"
        assert (tmp_path / "run_manifest.json").exists()
        assert (tmp_path / "session_trace.jsonl").exists()
        assert (tmp_path / "experience_records.jsonl").exists()
        assert (tmp_path / "strategy_lineage.json").exists()
        assert (tmp_path / "model_evaluation.json").exists()
        assert (tmp_path / "benchmark_scorecard.json").exists()

        # Check that SHA-256 hashes are recorded
        for name, file_hash in manifest.file_hashes.items():
            assert len(file_hash) == 64
            assert (tmp_path / name).exists()

    def test_strategy_provenance_validation(self) -> None:
        valid_lineage = StrategyLineage(
            strategy_id="s1",
            origin="reflection",
            source_experience_ids=("exp_1",),
            source_session_ids=("sess_1",),
            created_by="learning_pipeline",
            manual_override=False,
            verified=True,
        )
        assert validate_strategy_provenance(valid_lineage) is True

        # Contaminated by manual override
        manual_lineage = StrategyLineage(
            strategy_id="s2",
            origin="manual",
            source_experience_ids=(),
            created_by="developer",
            manual_override=True,
            verified=True,
        )
        assert validate_strategy_provenance(manual_lineage) is False

        # Unverified outcome
        unverified_lineage = StrategyLineage(
            strategy_id="s3",
            origin="reflection",
            source_experience_ids=("exp_3",),
            manual_override=False,
            verified=False,
        )
        assert validate_strategy_provenance(unverified_lineage) is False


class TestLearningPluginLifecycle:
    """Validate plugin hooks, idempotency, and lifecycle metrics."""

    def test_hook_event_idempotency(self, tmp_path: Path) -> None:
        from extensions.learning.plugin import LearningPlugin

        engine = LearningEngine(db_path=str(tmp_path / "plugin_test.sqlite"))
        engine.startup()
        plugin = LearningPlugin(engine=engine)

        class MockContext:
            def __init__(self) -> None:
                self.session_id = "sess_idem_001"
                self.agent_id = "agent_idem"

        class MockEvent:
            def __init__(self, t_id: str, attempt: int = 1) -> None:
                self.tool_call_id = t_id
                self.attempt_id = attempt
                self.tool_name = "volume.mute"
                self.tool_args = {"mute": True}
                self.tool_result = {"success": True, "value": "Volume muted"}
                self.user_input = "mute volume"
                self.claimed_outcome = "Volume is muted"

        ctx = MockContext()
        ev1 = MockEvent("call_123", attempt=1)
        ev2 = MockEvent("call_123", attempt=1)  # Duplicate event

        plugin.after_tool_call(ev1, ctx)
        initial_experiences = len(engine._db.list_experiences())

        # Second event with identical (tool_call_id, attempt_id) should be deduplicated
        plugin.after_tool_call(ev2, ctx)
        assert len(engine._db.list_experiences()) == initial_experiences

        # Different attempt or tool_call_id is allowed
        ev3 = MockEvent("call_123", attempt=2)
        plugin.after_tool_call(ev3, ctx)
        assert len(engine._db.list_experiences()) == initial_experiences + 1

        metrics = plugin.get_metrics()
        assert metrics["hook_events_received"] == 3
        assert metrics["tool_calls_recorded"] == 2


class TestCLIIntegration:
    """Validate status and demo CLI subcommands."""

    def test_cli_status_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        engine = LearningEngine(db_path=str(tmp_path / "cli_status.sqlite"))
        engine.startup()

        code = handle_status(engine, as_json=True)
        assert code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "healthy"
        assert "hardware" in data
        assert "experiences_count" in data
        assert "strategies_count" in data

    def test_cli_demo_json_and_deterministic_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = handle_demo(as_json=True, mode="deterministic")
        assert code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "passed"
        assert data["learning_effect"] == "proven"
        assert "scenarios" in data
        assert len(data["scenarios"]) == 8
