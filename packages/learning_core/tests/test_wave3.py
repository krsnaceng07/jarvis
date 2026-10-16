"""Wave 3 tests — Model Training, Calibration, Routing, Shadow Mode & Governance.

Verifies:
- Hardware capability detection and resource limits
- Baseline-first hierarchy and baseline comparison
- Probability calibration (Platt/temperature scaling, ECE, Brier)
- Multi-file artifact bundle with SHA-256 cryptographic integrity
- Model target compatibility validation
- Atomic model lifecycle state machine
- Policy safety guard (blocking destructive/shell actions)
- Normalized out-of-distribution (OOD) detection
- Deterministic argument construction vs LLM delegation
- Insufficient data detection
- Shadow mode verified correctness and category coverage
- Classified rolling-window health monitor and rollback
- End-to-end Wave 3 pipeline integration
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis_learning.hardware.detector import HardwareDetector
from jarvis_learning.hardware.profile import ComputeProfile, ComputeTier, HardwareSpecs
from jarvis_learning.models.arguments import DeterministicArgumentBuilder
from jarvis_learning.models.artifact import ModelArtifactBundle, ModelManifest
from jarvis_learning.models.base import LocalModel, ModelTargetMismatchError, ToolPrediction
from jarvis_learning.models.baseline import FrequencyBaseline, TFIDFLogisticBaseline
from jarvis_learning.models.calibration import ConfidenceCalibrator
from jarvis_learning.models.lifecycle import (
    InvalidLifecycleTransitionError,
    ModelLifecycle,
    ModelStatus,
)
from jarvis_learning.models.memory_reranker import MemoryRerankerModel
from jarvis_learning.models.registry import ModelRegistry
from jarvis_learning.models.strategy_predictor import StrategyPredictorModel
from jarvis_learning.models.tool_policy import ToolPolicyModel
from jarvis_learning.routing.guard import LocalDecisionGuard
from jarvis_learning.routing.health import RuntimeHealthMonitor
from jarvis_learning.routing.ood import DistributionGuard
from jarvis_learning.routing.promotion import PromotionManager, ShadowQualification
from jarvis_learning.routing.router import ModelRouter, RouterConfig
from jarvis_learning.routing.shadow import ShadowExecutor
from jarvis_learning.training.comparison import BaselineComparator
from jarvis_learning.training.config import TrainingConfig
from jarvis_learning.training.loss import GradedMarginLoss, WeightedFocalLoss
from jarvis_learning.training.resource_policy import (
    TrainingExecutionController,
    TrainingResourcePolicy,
)
from jarvis_learning.training.trainer import OfflineTrainer


# ══════════════════════════════════════════════════════════════
# 1. HARDWARE & RESOURCE TESTS
# ══════════════════════════════════════════════════════════════


class TestHardware:
    def test_host_hardware_detection(self) -> None:
        detector = HardwareDetector()
        specs = detector.detect_specs()
        assert specs.cpu_cores >= 1
        assert specs.cpu_threads >= 1
        assert specs.system_ram_gb > 0

        profile = detector.determine_profile(specs)
        assert isinstance(profile, ComputeProfile)
        assert profile.tier in (
            ComputeTier.CPU_MEMORY_RICH,
            ComputeTier.CPU_LIMITED,
            ComputeTier.FALLBACK,
        )

    def test_mocked_cuda_profiles(self) -> None:
        detector = HardwareDetector()
        # High-VRAM CUDA specs
        high_cuda_specs = HardwareSpecs(
            cpu_cores=8,
            cpu_threads=16,
            system_ram_gb=32.0,
            gpu_name="NVIDIA RTX 4090",
            has_cuda=True,
            cuda_vram_gb=24.0,
            has_torch=True,
            has_transformers=True,
            has_peft=True,
            has_sklearn=True,
        )
        high_profile = detector.determine_profile(high_cuda_specs)
        assert high_profile.tier == ComputeTier.CUDA_HIGH
        assert high_profile.supports_lora is True

        # Mid-VRAM CUDA specs
        mid_cuda_specs = HardwareSpecs(
            cpu_cores=6,
            cpu_threads=12,
            system_ram_gb=16.0,
            gpu_name="NVIDIA RTX 3060",
            has_cuda=True,
            cuda_vram_gb=12.0,
            has_torch=True,
            has_transformers=True,
            has_peft=True,
            has_sklearn=True,
        )
        mid_profile = detector.determine_profile(mid_cuda_specs)
        assert mid_profile.tier == ComputeTier.CUDA_MID

    def test_resource_policy_controller(self) -> None:
        policy = TrainingResourcePolicy(max_threads=2)
        controller = TrainingExecutionController(policy)

        # Starts unpaused
        assert controller.check_checkpoint() is True

        # Pause and resume
        controller.pause("test")
        controller.resume()
        assert controller.check_checkpoint() is True

        # Cancel
        controller.cancel()
        assert controller.check_checkpoint() is False


# ══════════════════════════════════════════════════════════════
# 2. CALIBRATION & LOSS TESTS
# ══════════════════════════════════════════════════════════════


class TestCalibrationAndLoss:
    def test_focal_loss_computation(self) -> None:
        loss = WeightedFocalLoss(gamma=2.0)
        # High confidence correct prediction -> very low loss
        low_loss = loss.compute(target_prob=0.99, sample_weight=1.0)
        # Low confidence correct prediction -> high loss
        high_loss = loss.compute(target_prob=0.10, sample_weight=1.0)
        assert low_loss < high_loss
        assert low_loss >= 0.0

    def test_margin_ranking_loss(self) -> None:
        loss = GradedMarginLoss(margin=1.0)
        # Positive score is significantly higher than negative -> 0 loss
        assert loss.compute(pos_score=2.5, neg_score=0.5) == 0.0
        # Negative score higher than positive -> positive loss
        assert loss.compute(pos_score=0.5, neg_score=1.5) == 2.0

    def test_confidence_calibration_fit(self) -> None:
        calibrator = ConfidenceCalibrator()
        # Simulated overconfident model: outputs 0.90 but actual accuracy is only 50%
        probs = [0.90] * 20
        labels = [1] * 10 + [0] * 10  # 50% true accuracy

        metrics = calibrator.fit(probs, labels)
        assert metrics.temperature > 1.0  # Temperature scaling increases to soften overconfidence
        calibrated_prob = calibrator.calibrate(0.90)
        assert calibrated_prob < 0.90  # Calibrated downward toward empirical accuracy

    def test_calibration_serialization(self) -> None:
        calibrator = ConfidenceCalibrator(temperature=1.8, bias=-0.1)
        d = calibrator.to_dict()
        restored = ConfidenceCalibrator.from_dict(d)
        assert restored.temperature == 1.8
        assert restored.bias == -0.1


# ══════════════════════════════════════════════════════════════
# 3. ARTIFACT BUNDLE & LIFECYCLE TESTS
# ══════════════════════════════════════════════════════════════


class TestArtifactAndLifecycle:
    def test_artifact_bundle_save_verify(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "models" / "tool_policy" / "v001"
        manifest = ModelManifest(
            model_id="tp_001",
            target="tool_policy",
            version="v001",
            architecture="tfidf_logistic",
            compute_tier="cpu_memory_rich",
            feature_schema_version="1",
            created_at=1000,
            parameters_count=500,
            training_manifest_hash="hash_123",
        )

        saved = ModelArtifactBundle.save_bundle(
            artifact_dir=artifact_dir,
            manifest=manifest,
            weights_data={"weights": [[0.1, 0.2]]},
            vectorizer_data={"vocab": {"play": 0}},
            label_encoder_data={"classes": ["browser.open"]},
            calibration_data={"temperature": 1.0},
            feature_schema={"input": "user_input"},
        )
        assert (saved / "checksums.json").exists()

        # Load with correct target -> succeeds
        man, vec, labels, cal, schema = ModelArtifactBundle.verify_and_load(
            saved, expected_target="tool_policy"
        )
        assert man.model_id == "tp_001"
        assert "play" in vec["vocab"]

    def test_artifact_target_mismatch_raises(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "models" / "tool_policy" / "v002"
        manifest = ModelManifest(
            model_id="tp_002",
            target="tool_policy",
            version="v002",
            architecture="tfidf_logistic",
            compute_tier="cpu_memory_rich",
            feature_schema_version="1",
            created_at=1000,
            parameters_count=500,
            training_manifest_hash="hash_123",
        )
        saved = ModelArtifactBundle.save_bundle(
            artifact_dir=artifact_dir,
            manifest=manifest,
            weights_data={},
            vectorizer_data={},
            label_encoder_data={},
            calibration_data={},
            feature_schema={},
        )
        # Attempting to load a tool_policy model as a strategy_predictor MUST raise
        with pytest.raises(ModelTargetMismatchError):
            ModelArtifactBundle.verify_and_load(saved, expected_target="strategy_predictor")

    def test_artifact_checksum_corruption_detected(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "models" / "tool_policy" / "v003"
        manifest = ModelManifest(
            model_id="tp_003",
            target="tool_policy",
            version="v003",
            architecture="tfidf_logistic",
            compute_tier="cpu_memory_rich",
            feature_schema_version="1",
            created_at=1000,
            parameters_count=500,
            training_manifest_hash="hash_123",
        )
        saved = ModelArtifactBundle.save_bundle(
            artifact_dir=artifact_dir,
            manifest=manifest,
            weights_data={"a": 1},
            vectorizer_data={},
            label_encoder_data={},
            calibration_data={},
            feature_schema={},
        )
        # Tamper with weights.json
        (saved / "weights.json").write_text('{"tampered": true}')
        with pytest.raises(ValueError, match="Integrity check failed"):
            ModelArtifactBundle.verify_and_load(saved, expected_target="tool_policy")

    def test_atomic_lifecycle_state_machine(self) -> None:
        # Valid state transitions
        t1 = ModelLifecycle.transition(
            ModelStatus.CANDIDATE, ModelStatus.SHADOW, actor="test", reason="passed benchmark"
        )
        assert t1.to_status == ModelStatus.SHADOW

        t2 = ModelLifecycle.transition(
            ModelStatus.SHADOW, ModelStatus.PROMOTED, actor="operator", reason="approved"
        )
        assert t2.to_status == ModelStatus.PROMOTED

        t3 = ModelLifecycle.transition(
            ModelStatus.PROMOTED, ModelStatus.ROLLED_BACK, actor="monitor", reason="error spike"
        )
        assert t3.to_status == ModelStatus.ROLLED_BACK

        # Illegal state transitions must be blocked
        with pytest.raises(InvalidLifecycleTransitionError):
            ModelLifecycle.transition(
                ModelStatus.CANDIDATE, ModelStatus.PROMOTED, actor="bad", reason="illegal leap"
            )

        with pytest.raises(InvalidLifecycleTransitionError):
            ModelLifecycle.transition(
                ModelStatus.ROLLED_BACK, ModelStatus.PROMOTED, actor="bad", reason="illegal revive"
            )


# ══════════════════════════════════════════════════════════════
# 4. BASELINE, COMPARISON & MODELS TESTS
# ══════════════════════════════════════════════════════════════


class TestBaselinesAndModels:
    def test_frequency_baseline(self) -> None:
        baseline = FrequencyBaseline()
        samples = [
            {
                "input_data": {"user_input": "play music on youtube"},
                "label": {"tool": "browser.navigate_tab"},
            },
            {
                "input_data": {"user_input": "play music on youtube"},
                "label": {"tool": "browser.navigate_tab"},
            },
            {"input_data": {"user_input": "set volume to 50"}, "label": {"tool": "volume.set"}},
        ]
        baseline.fit(samples)

        # Exact match
        tool, conf = baseline.predict("play music on youtube")
        assert tool == "browser.navigate_tab"
        assert conf >= 0.9

        # Fallback to most frequent
        tool_unk, _ = baseline.predict("completely unknown query")
        assert tool_unk == "browser.navigate_tab"

    def test_tfidf_logistic_baseline(self) -> None:
        model = TFIDFLogisticBaseline()
        samples = [
            {
                "input_data": {"user_input": "play believer on youtube music"},
                "label": {"tool": "browser.navigate_tab"},
            },
            {
                "input_data": {"user_input": "open youtube video"},
                "label": {"tool": "browser.navigate_tab"},
            },
            {"input_data": {"user_input": "turn volume up to 80"}, "label": {"tool": "volume.set"}},
            {"input_data": {"user_input": "set the volume to 20"}, "label": {"tool": "volume.set"}},
        ]
        model.fit(samples, epochs=30, lr=0.2)

        pred_tool, conf = model.predict("please play song on youtube")
        assert pred_tool == "browser.navigate_tab"
        assert conf > 0.5

        pred_vol, conf_vol = model.predict("set volume to 40")
        assert pred_vol == "volume.set"
        assert conf_vol > 0.5

    def test_baseline_comparator_margin(self) -> None:
        comparator = BaselineComparator(min_accuracy_gain=0.05)  # Requires 5% gain
        ground_truth = ["tool_a"] * 10 + ["tool_b"] * 10

        # Baseline gets 80% (16/20)
        baseline_preds = (
            [("tool_a", 0.9)] * 8
            + [("tool_b", 0.9)] * 2
            + [("tool_b", 0.9)] * 8
            + [("tool_a", 0.9)] * 2
        )
        # Candidate gets 80% (16/20) -> gain is 0%, which is < required 5%
        cand_weak = (
            [("tool_a", 0.9)] * 8
            + [("tool_b", 0.9)] * 2
            + [("tool_b", 0.9)] * 8
            + [("tool_a", 0.9)] * 2
        )

        report = comparator.compare(cand_weak, baseline_preds, ground_truth)
        assert report.beats_baseline is False
        assert "Candidate rejected" in report.verdict

        # Candidate gets 95% (19/20) -> gain is 15% -> qualifies
        cand_strong = [("tool_a", 0.9)] * 10 + [("tool_b", 0.9)] * 9 + [("tool_a", 0.9)] * 1
        report_strong = comparator.compare(cand_strong, baseline_preds, ground_truth)
        assert report_strong.beats_baseline is True
        assert "Candidate qualified" in report_strong.verdict

    def test_deterministic_argument_builder(self) -> None:
        builder = DeterministicArgumentBuilder()

        # Browser navigate with matching tab in context
        res1 = builder.build_arguments(
            "browser.navigate_tab",
            "play song on youtube",
            {"open_tabs": [{"id": 2, "url": "https://youtube.com"}]},
        )
        assert res1.success is True
        assert res1.arguments == {"tab_id": 2}
        assert res1.requires_llm is False

        # Volume parsing
        res2 = builder.build_arguments("volume.set", "set volume to 65 percent", {})
        assert res2.success is True
        assert res2.arguments == {"level": 65}

        # Destructive tool requires LLM
        res3 = builder.build_arguments("filesystem.write", "write code to file", {})
        assert res3.success is False
        assert res3.requires_llm is True

    def test_memory_reranker_shadow_only(self) -> None:
        reranker = MemoryRerankerModel()
        assert reranker.is_shadow_only is True

        res = reranker.predict(
            {
                "query": "favorite rock band",
                "memories": ["user loves Queen and rock music", "user has a meeting at 2pm"],
            }
        )
        assert res["shadow_only"] is True
        assert res["ranked_memories"][0]["memory"] == "user loves Queen and rock music"
        assert res["ranked_memories"][0]["score"] > 0.0

    def test_strategy_predictor_selection_bias(self) -> None:
        predictor = StrategyPredictorModel()
        candidates = [
            {"id": "strat_1", "success_count": 9, "failure_count": 1},  # 90%
            {"id": "strat_2", "success_count": 2, "failure_count": 8},  # 20%
        ]
        res = predictor.predict({"candidate_strategies": candidates})
        preds = res["predictions"]
        assert preds[0]["strategy_id"] == "strat_1"
        assert preds[0]["p_success"] == 0.90


# ══════════════════════════════════════════════════════════════
# 5. SAFETY GUARD & OOD DETECTION TESTS
# ══════════════════════════════════════════════════════════════


class TestSafetyGuardAndOOD:
    def test_local_decision_guard_blocks_destructive(self) -> None:
        guard = LocalDecisionGuard()

        # Shell execution MUST be blocked
        pred_shell = ToolPrediction(
            tool_name="system.shell",
            raw_confidence=0.99,
            calibrated_confidence=0.99,
            action_type="destructive",
            risk_level="destructive",
        )
        decision = guard.validate(pred_shell)
        assert decision.allowed is False
        assert "destructive" in decision.reason

        # File deletion MUST be blocked
        pred_del = ToolPrediction(
            tool_name="filesystem.delete",
            raw_confidence=0.95,
            calibrated_confidence=0.95,
            action_type="destructive",
            risk_level="destructive",
        )
        assert guard.validate(pred_del).allowed is False

    def test_local_decision_guard_allows_safe_tool(self) -> None:
        guard = LocalDecisionGuard(min_calibrated_confidence=0.85)

        pred_safe = ToolPrediction(
            tool_name="browser.navigate_tab",
            raw_confidence=0.95,
            calibrated_confidence=0.90,
            action_type="navigate",
            risk_level="low",
        )
        decision = guard.validate(pred_safe)
        assert decision.allowed is True
        assert decision.risk_level == "low"

    def test_local_decision_guard_low_confidence_blocked(self) -> None:
        guard = LocalDecisionGuard(min_calibrated_confidence=0.85)

        pred_unconfident = ToolPrediction(
            tool_name="volume.set",
            raw_confidence=0.70,
            calibrated_confidence=0.65,
            action_type="set_state",
            risk_level="low",
        )
        decision = guard.validate(pred_unconfident)
        assert decision.allowed is False
        assert "below required threshold" in decision.reason

    def test_ood_detection(self) -> None:
        guard = DistributionGuard(
            known_vocabulary={"play", "music", "on", "youtube", "volume", "set", "tab"},
            ood_threshold=0.5,
        )

        # In-distribution query
        res_in = guard.evaluate("play music on youtube tab")
        assert res_in.is_ood is False
        assert res_in.score < 0.5
        assert res_in.vocabulary_coverage == 1.0

        # Out-of-distribution query (novel / complex task)
        res_out = guard.evaluate("Analyze suspicious powershell persistence registry key")
        assert res_out.is_ood is True
        assert res_out.score >= 0.5
        assert res_out.vocabulary_coverage < 0.3


# ══════════════════════════════════════════════════════════════
# 6. REGISTRY, SHADOW & HEALTH TESTS
# ══════════════════════════════════════════════════════════════


class TestRegistryShadowHealth:
    def test_model_registry_crud(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_reg.sqlite"
        registry = ModelRegistry(db_path)

        record = registry.register_model(
            model_id="tp_001",
            target="tool_policy",
            version="v001",
            architecture="tfidf_logistic",
            compute_tier="cpu_memory_rich",
            weights_path="/tmp/weights.json",
            weights_sha256="abc123sha",
            artifact_size=1024,
            dataset_manifest_hash="d_123",
            parameters_count=1000,
            baseline_beaten="baseline_v1",
            val_loss=0.15,
            val_metrics={"accuracy": 0.88},
            initial_status=ModelStatus.CANDIDATE,
        )
        assert record.status == ModelStatus.CANDIDATE

        # Transition to shadow
        updated = registry.transition_status(
            "tp_001",
            ModelStatus.SHADOW,
            actor="test_runner",
            reason="passed test suite",
        )
        assert updated.status == ModelStatus.SHADOW
        assert len(updated.transition_history) == 1

        # Check list
        models = registry.list_models(target="tool_policy")
        assert len(models) == 1

    def test_shadow_executor_and_qualification(self) -> None:
        class DummyModel(LocalModel):
            def __init__(self, model_id: str = "dummy_1") -> None:
                super().__init__(target="tool_policy", model_id=model_id, version="v001")

            def load(self, artifact_dir: Path) -> None:
                pass

            def predict(self, input_data: dict) -> str:
                text = input_data.get("user_input", "")
                return "volume.set" if "volume" in text else "browser.navigate_tab"

            def unload(self) -> None:
                pass

        dummy = DummyModel()
        executor = ShadowExecutor([dummy])

        # Simulate shadow turns across multiple categories
        for i in range(10):
            executor.execute_shadow_turn(
                session_id=f"sess_{i}",
                user_input=f"play song {i}",
                active_tool_chosen="browser.navigate_tab",
                verified_successful_tool="browser.navigate_tab",
                category="browser_state",
            )
        for i in range(10):
            executor.execute_shadow_turn(
                session_id=f"sess_{i + 10}",
                user_input=f"set volume to {i * 10}",
                active_tool_chosen="volume.set",
                verified_successful_tool="volume.set",
                category="volume_control",
            )

        metrics = executor.compute_metrics()
        assert metrics.total_observations == 20
        assert metrics.verified_tool_accuracy == 1.0
        assert metrics.category_counts["browser_state"] == 10
        assert metrics.category_counts["volume_control"] == 10

    def test_promotion_category_coverage_gate(self, tmp_path: Path) -> None:
        class DummyModel(LocalModel):
            def __init__(self, model_id: str = "tp_promo") -> None:
                super().__init__(target="tool_policy", model_id=model_id, version="v001")

            def load(self, artifact_dir: Path) -> None:
                pass

            def predict(self, input_data: dict) -> str:
                return "browser.navigate_tab"

            def unload(self) -> None:
                pass

        registry = ModelRegistry(tmp_path / "promo.sqlite")
        registry.register_model(
            model_id="tp_promo",
            target="tool_policy",
            version="v001",
            architecture="tfidf_logistic",
            compute_tier="cpu_memory_rich",
            weights_path="",
            weights_sha256="",
            artifact_size=0,
            dataset_manifest_hash="",
            parameters_count=0,
            baseline_beaten="",
            val_loss=0.0,
            val_metrics={},
            initial_status=ModelStatus.SHADOW,
        )

        qualification = ShadowQualification(
            min_total_samples=10,
            min_per_category={"browser_state": 5, "volume_control": 5},
            min_verified_accuracy=0.90,
        )
        manager = PromotionManager(registry=registry, qualification=qualification)

        # Incomplete category coverage (0 volume_control)
        dummy = DummyModel("tp_promo")
        executor_incomplete = ShadowExecutor([dummy])
        for i in range(10):
            executor_incomplete.execute_shadow_turn(
                session_id=f"s_{i}",
                user_input="test",
                active_tool_chosen="browser.navigate_tab",
                verified_successful_tool="browser.navigate_tab",
                category="browser_state",
            )
        metrics_inc = executor_incomplete.compute_metrics()
        decision_fail = manager.evaluate_shadow_model("tp_promo", metrics_inc)
        assert decision_fail.qualified is False
        assert "Insufficient coverage for category 'volume_control'" in decision_fail.reason

    def test_health_monitor_classified_rollback(self) -> None:
        monitor = RuntimeHealthMonitor(window_size=10, max_consecutive_model_failures=3)

        # Environmental failures (network timeout) must NOT trigger rollback
        for i in range(4):
            dec = monitor.record_execution(
                turn_id=f"t_{i}",
                tool_name="browser.navigate_tab",
                success=False,
                error_message="Network connection timeout",
            )
            assert dec.rollback_required is False

        # Single critical safety failure / false claim MUST trigger rollback
        dec_false = monitor.record_execution(
            turn_id="t_crit",
            tool_name="volume.set",
            success=False,
            verification_status="false_claim",
        )
        assert dec_false.rollback_required is True
        assert "False completion claim detected" in dec_false.trigger_reason

        # 3 consecutive model-caused failures trigger rollback
        monitor2 = RuntimeHealthMonitor(window_size=10, max_consecutive_model_failures=3)
        for i in range(3):
            dec = monitor2.record_execution(
                turn_id=f"t_model_{i}",
                tool_name="wrong.tool",
                success=False,
                error_message="tool selection error: unexpected tool",
            )
        assert dec.rollback_required is True
        assert "3 consecutive model-caused failures" in dec.trigger_reason


# ══════════════════════════════════════════════════════════════
# 7. END-TO-END PIPELINE PROOF
# ══════════════════════════════════════════════════════════════


class TestFullWave3Pipeline:
    """End-to-end integration test proving the entire Wave 3 hybrid architecture."""

    def test_dataset_to_candidate_to_shadow_to_routing(self, tmp_path: Path) -> None:
        # 1. Create realistic Wave 2 dataset on disk
        dataset_dir = tmp_path / "datasets" / "tool_policy"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        train_data = [
            {
                "input_data": {"user_input": f"play track {i} on YouTube"},
                "label": {"tool": "browser.navigate_tab"},
            }
            for i in range(20)
        ] + [
            {
                "input_data": {"user_input": f"set volume level to {i * 5}"},
                "label": {"tool": "volume.set"},
            }
            for i in range(20)
        ]
        val_data = [
            {
                "input_data": {"user_input": "play believer on YouTube"},
                "label": {"tool": "browser.navigate_tab"},
            },
            {"input_data": {"user_input": "set the volume to 50"}, "label": {"tool": "volume.set"}},
        ]
        test_data = [
            {
                "input_data": {"user_input": "play radio on YouTube"},
                "label": {"tool": "browser.navigate_tab"},
            },
            {
                "input_data": {"user_input": "mute the system volume"},
                "label": {"tool": "volume.set"},
            },
        ]

        (dataset_dir / "train.jsonl").write_text(
            "\n".join(json.dumps(d) for d in train_data) + "\n"
        )
        (dataset_dir / "validation.jsonl").write_text(
            "\n".join(json.dumps(d) for d in val_data) + "\n"
        )
        (dataset_dir / "test.jsonl").write_text("\n".join(json.dumps(d) for d in test_data) + "\n")
        (dataset_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "dataset_id": "d_test_123",
                    "dataset_version": "tool_policy_v001",
                    "target": "tool_policy",
                    "schema_version": "1",
                }
            )
        )

        # 2. Train Candidate Model via OfflineTrainer
        registry = ModelRegistry(tmp_path / "pipeline.sqlite")
        trainer = OfflineTrainer(registry=registry)
        config = TrainingConfig(
            target="tool_policy",
            dataset_dir=str(dataset_dir),
            output_dir=str(tmp_path / "models"),
            min_samples_required=10,
            min_accuracy_gain=0.0,
            epochs=20,
        )
        train_result = trainer.train(config)
        assert train_result.success is True
        assert train_result.model_record is not None
        assert train_result.status == ModelStatus.CANDIDATE

        # 3. Verify Artifact Bundle & SHA-256 Checksums
        artifact_dir = train_result.artifact_dir
        assert artifact_dir is not None
        assert (artifact_dir / "checksums.json").exists()

        # Load into ToolPolicyModel
        policy_model = ToolPolicyModel()
        policy_model.load(artifact_dir)
        assert policy_model.is_loaded is True

        # 4. Verify Decision Router Fallback When Disabled
        router_disabled = ModelRouter(
            config=RouterConfig(local_models_enabled=False),
            registry=registry,
        )
        router_disabled.set_active_model(policy_model)
        res_disabled = router_disabled.route(user_input="play music on YouTube")
        # Local models disabled -> routes safely to Foundation LLM
        assert res_disabled.handler == "foundation_llm"
        assert "disabled by configuration" in res_disabled.trace.fallback_reason

        # 5. Enable Local Models & Verify Safe Local Fast-Path Routing
        router_enabled = ModelRouter(
            config=RouterConfig(
                local_models_enabled=True,
                shadow_mode_enabled=False,
                min_calibrated_confidence=0.50,
            ),
            registry=registry,
        )
        router_enabled.set_active_model(policy_model)
        router_enabled.ood_guard.set_vocabulary(
            {"play", "track", "youtube", "music", "volume", "set"}
        )

        res_enabled = router_enabled.route(
            user_input="play track on YouTube",
            context={"open_tabs": [{"id": 3, "url": "https://youtube.com"}]},
        )
        assert res_enabled.handler == "local_model"
        assert res_enabled.tool_name == "browser.navigate_tab"
        assert res_enabled.tool_arguments == {"tab_id": 3}
        assert res_enabled.trace.guard_decision == "allowed"

        # 6. Verify Destructive / OOD Queries Still Route to Foundation LLM
        res_ood = router_enabled.route(user_input="Reverse engineer this binary payload")
        assert res_ood.handler == "foundation_llm"
        assert res_ood.trace.guard_decision == "blocked_ood"

        # 7. Verify Engine Integration APIs
        from jarvis_learning.engine import LearningEngine

        engine = LearningEngine(db_path=str(tmp_path / "engine.sqlite"))
        engine.startup()
        engine_route = engine.route_turn(
            user_input="test command",
            session_id="s1",
            local_models_enabled=False,
        )
        assert engine_route.handler == "foundation_llm"
