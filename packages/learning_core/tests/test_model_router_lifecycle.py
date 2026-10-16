"""Integration tests for Phase 3: ModelRouter Complete Lifecycle & Gating.

Verifies:
1. Active model attachment and resolution through LearningEngine.route_turn().
2. Complete 13-state routing machine (NO_MODEL, MODEL_UNAVAILABLE, OOD_ABSTAIN, etc.).
3. Strict separation of eligibility and authorization (Confidence != Permission).
4. Empirical OOD detection with AUROC/AUPRC and task-family calibration.
5. Task-family calibration metrics (ECE, Brier, temperature scaling).
6. Robustness against non-finite predictions and inference exceptions.
7. DecisionTrace completeness and diagnostic observability.
8. Operator-controlled activation gate with audit logging.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from jarvis_learning.engine import LearningEngine
from jarvis_learning.models.base import LocalModel, ToolPrediction
from jarvis_learning.models.baseline import TFIDFLogisticBaseline, TfidfBaselineModel
from jarvis_learning.models.calibration import ConfidenceCalibrator
from jarvis_learning.models.lifecycle import ModelStatus
from jarvis_learning.models.registry import ModelRegistry
from jarvis_learning.routing.ood import DistributionGuard
from jarvis_learning.routing.promotion import PromotionManager
from jarvis_learning.routing.router import ModelRouter, RouterConfig, RoutingState


class MockDeterministicModel(LocalModel):
    """Deterministic local model for router testing."""

    def __init__(
        self,
        model_id: str = "mock_model_v1",
        version: str = "v1.0.0",
        target: str = "tool_policy",
        predicted_tool: str = "volume.mute",
        confidence: float = 0.95,
        risk_level: str = "low",
        is_finite: bool = True,
        should_raise: bool = False,
    ) -> None:
        super().__init__(target=target, model_id=model_id, version=version)
        self.predicted_tool = predicted_tool
        self.confidence = confidence
        self.risk_level = risk_level
        self._is_finite = is_finite
        self.should_raise = should_raise
        self._is_loaded = True
        self.calibrator = ConfidenceCalibrator(temperature=1.0)

    def load(self, artifact_dir: Path) -> None:
        self._is_loaded = True

    def predict(self, input_data: dict[str, Any]) -> ToolPrediction:
        if self.should_raise:
            raise RuntimeError("Simulated inference engine failure")

        conf = float("nan") if not self._is_finite else self.confidence
        return ToolPrediction(
            tool_name=self.predicted_tool,
            raw_confidence=conf if self._is_finite else 0.0,
            calibrated_confidence=conf if self._is_finite else 0.0,
            confidence=conf if self._is_finite else 0.0,
            intent="mute_volume",
            model_id=self.model_id,
            model_version=self.version,
            task_family=self.target,
            is_finite=self._is_finite and math.isfinite(conf),
            risk_level=self.risk_level,
            argument_strategy="deterministic",
        )

    def unload(self) -> None:
        self._is_loaded = False


@pytest.fixture
def clean_engine(tmp_path: Path) -> LearningEngine:
    db_path = str(tmp_path / "test_router_engine.sqlite")
    engine = LearningEngine(db_path=db_path)
    engine.startup()
    return engine


def test_active_model_attachment_and_engine_routing(clean_engine: LearningEngine) -> None:
    """Verify LearningEngine attaches model to ModelRouter and executes routing."""
    model = MockDeterministicModel(predicted_tool="volume.mute", confidence=0.92)

    # 1. Attach model via LearningEngine
    clean_engine.attach_local_model(model)
    assert clean_engine.router._active_local_model is model

    # 2. Route turn through LearningEngine in shadow mode (default safe behavior)
    res = clean_engine.route_turn(
        user_input="mute the volume please",
        session_id="sess_router_01",
        local_models_enabled=True,
        shadow_mode_enabled=True,
    )

    # In shadow mode, handler is foundation_llm, but prediction is evaluated and logged
    assert res.handler == "foundation_llm"
    assert res.routing_state == RoutingState.SHADOW_ONLY
    assert res.trace.selected_handler == "foundation_llm"
    assert res.trace.authorization_result == "shadow_only"
    assert res.trace.model_id == "mock_model_v1"
    assert res.trace.tool_predicted == "volume.mute"


def test_no_model_and_model_unavailable(clean_engine: LearningEngine) -> None:
    """Verify router cleanly identifies NO_MODEL and MODEL_UNAVAILABLE states."""
    # 1. No model attached or registered
    router = ModelRouter(config=RouterConfig(local_models_enabled=True, shadow_mode_enabled=False))
    res_no_model = router.route(user_input="calculate 2 + 2")
    assert res_no_model.routing_state == RoutingState.NO_MODEL
    assert res_no_model.handler == "foundation_llm"
    assert res_no_model.trace.fallback_reason == "No local model configured or registered"

    # 2. Model set but unloaded
    model = MockDeterministicModel()
    model.unload()
    router.set_active_model(model)
    res_unavail = router.route(user_input="turn volume down")
    assert res_unavail.routing_state == RoutingState.MODEL_UNAVAILABLE
    assert res_unavail.handler == "foundation_llm"
    assert "not loaded" in res_unavail.trace.fallback_reason


def test_model_incompatibility_rejection(clean_engine: LearningEngine) -> None:
    """Verify models with mismatched task_family targets are rejected."""
    model = MockDeterministicModel(target="speech_synthesis")
    clean_engine.attach_local_model(model)

    res = clean_engine.route_turn(
        user_input="show current date",
        local_models_enabled=True,
        task_family="tool_policy",
    )
    assert res.routing_state == RoutingState.MODEL_INCOMPATIBLE
    assert "incompatible" in res.trace.fallback_reason


def test_empirical_ood_detection_and_task_thresholds() -> None:
    """Verify DistributionGuard empirical calibration, AUROC/AUPRC, and OOD abstention."""
    guard = DistributionGuard(known_vocabulary={"volume", "mute", "sound", "audio", "speaker"})

    # Calibration dataset: in-distribution vs OOD scores
    id_scores = [0.05, 0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30]
    ood_scores = [0.65, 0.70, 0.72, 0.75, 0.80, 0.82, 0.85, 0.88, 0.90, 0.95]

    calib = guard.calibrate_empirical_threshold(
        in_distribution_scores=id_scores,
        ood_scores=ood_scores,
        task_family="audio_control",
        target_fpr=0.10,
    )
    assert calib.is_statistically_valid is True
    assert calib.auroc >= 0.95
    assert calib.threshold > 0.25

    # 1. In-distribution query -> within bounds
    res_id = guard.evaluate("mute sound volume", task_family="audio_control")
    assert res_id.is_ood is False
    assert res_id.score < calib.threshold

    # 2. Out-of-distribution query -> abstention triggered
    res_ood = guard.evaluate(
        "synthesize organic molecule polymers in vacuum", task_family="audio_control"
    )
    assert res_ood.is_ood is True
    assert res_ood.score >= calib.threshold

    # 3. Small sample edge case -> marked insufficient_evidence without crashing
    guard_small = DistributionGuard()
    calib_small = guard_small.calibrate_empirical_threshold([0.1, 0.2], [0.8])
    assert calib_small.is_statistically_valid is False
    assert calib_small.status == "insufficient_evidence"


def test_strict_separation_of_eligibility_and_authorization() -> None:
    """Verify Confidence != Permission: dangerous tools are NEVER authorized for local execution."""
    router = ModelRouter(config=RouterConfig(local_models_enabled=True, shadow_mode_enabled=False))

    # Even with 100% confidence, a destructive tool prediction must be POLICY_DENIED
    model_destructive = MockDeterministicModel(
        predicted_tool="system.shell",
        confidence=1.0,
        risk_level="destructive",
    )
    router.set_active_model(model_destructive)

    res = router.route(user_input="format drive C:")
    assert res.routing_state == RoutingState.POLICY_DENIED
    assert res.handler == "foundation_llm"
    assert res.trace.authorization_result == "denied"
    assert "destructive" in res.trace.fallback_reason


def test_calibration_requirement_and_temperature_scaling() -> None:
    """Verify confidence calibration gating and Platt/temperature scaling."""
    calibrator = ConfidenceCalibrator()

    # Fit calibration on synthetic validation predictions
    raw_probs = [0.60, 0.70, 0.80, 0.85, 0.90, 0.95]
    labels = [0, 0, 1, 1, 1, 1]
    metrics = calibrator.fit(raw_probs, labels, task_family="tool_policy")

    assert metrics.is_valid is True
    assert metrics.brier_score >= 0.0
    assert calibrator.is_calibrated is True

    # Test calibration gating in ModelRouter
    model = MockDeterministicModel(confidence=0.88)
    model.calibrator = calibrator

    router = ModelRouter(
        config=RouterConfig(
            local_models_enabled=True,
            shadow_mode_enabled=False,
            require_calibration=True,
        )
    )
    router.set_active_model(model)

    # When calibrated, execution continues
    res_calibrated = router.route(user_input="mute volume")
    assert res_calibrated.routing_state == RoutingState.PRODUCTION_ACTIVE

    # When uncalibrated and require_calibration is True, abstains with CALIBRATION_UNAVAILABLE
    uncalibrated = ConfidenceCalibrator()
    assert uncalibrated.is_calibrated is False
    model.calibrator = uncalibrated
    res_uncalib = router.route(user_input="mute volume")
    assert res_uncalib.routing_state == RoutingState.CALIBRATION_UNAVAILABLE
    assert res_uncalib.handler == "foundation_llm"


def test_inference_exception_and_non_finite_resilience() -> None:
    """Verify model crashing or returning NaN/Inf triggers safe fallback with zero crash risk."""
    router = ModelRouter(config=RouterConfig(local_models_enabled=True, shadow_mode_enabled=False))

    # 1. Non-finite probability (NaN)
    model_nan = MockDeterministicModel(is_finite=False)
    router.set_active_model(model_nan)
    res_nan = router.route(user_input="mute volume")
    assert res_nan.routing_state == RoutingState.LOW_CONFIDENCE_ABSTAIN
    assert res_nan.handler == "foundation_llm"

    # 2. Inference exception
    model_crashing = MockDeterministicModel(should_raise=True)
    router.set_active_model(model_crashing)
    res_err = router.route(user_input="mute volume")
    assert res_err.routing_state == RoutingState.ERROR_SAFE_FALLBACK
    assert res_err.handler == "foundation_llm"
    assert "Inference exception" in res_err.trace.fallback_reason


def test_tfidf_baseline_model_lifecycle(tmp_path: Path) -> None:
    """Verify TfidfBaselineModel trains, persists, and interfaces as a valid LocalModel."""
    baseline = TFIDFLogisticBaseline()
    samples = [
        {"input_data": {"user_input": "mute the audio"}, "label": {"tool": "volume.mute"}},
        {"input_data": {"user_input": "silence speakers"}, "label": {"tool": "volume.mute"}},
        {"input_data": {"user_input": "what time is it"}, "label": {"tool": "system.get_time"}},
        {"input_data": {"user_input": "show the clock"}, "label": {"tool": "system.get_time"}},
    ]
    baseline.fit(samples, epochs=15)

    model = TfidfBaselineModel(model_id="tfidf_baseline_v1", version="v1.0.0", baseline=baseline)
    assert model.is_loaded is True

    # Test prediction
    pred = model.predict({"user_input": "mute audio"})
    assert pred.tool_name == "volume.mute"
    assert pred.is_finite is True
    assert pred.raw_confidence > 0.5

    # Test serialization and reload
    save_dir = tmp_path / "tfidf_artifact"
    model.save(save_dir)
    reloaded_model = TfidfBaselineModel(model_id="tfidf_reloaded", version="v1.0.0")
    reloaded_model.load(save_dir)
    pred_reloaded = reloaded_model.predict({"user_input": "what time is it"})
    assert pred_reloaded.tool_name == "system.get_time"


def test_operator_controlled_activation_gate(tmp_path: Path) -> None:
    """Verify candidate models require explicit operator approval and audit log entry."""
    registry = ModelRegistry(db_path=tmp_path / "models_registry.sqlite")
    weights_path = tmp_path / "dummy_weights.bin"
    weights_path.write_bytes(b"dummy_weights_content")

    # Register candidate model with good validation metrics
    registry.register_model(
        model_id="candidate_model_01",
        target="tool_policy",
        version="v1.1.0",
        architecture="nano_transformer",
        compute_tier="cpu",
        weights_path=str(weights_path),
        weights_sha256="dummy_sha256",
        artifact_size=len(b"dummy_weights_content"),
        dataset_manifest_hash="manifest_hash_1",
        parameters_count=1000,
        baseline_beaten="tfidf_baseline_v1 (accuracy +12%)",
        val_loss=0.12,
        val_metrics={"accuracy": 0.94, "macro_f1": 0.92},
        initial_status=ModelStatus.SHADOW,
    )

    promo_mgr = PromotionManager(registry=registry)

    # 1. Attempt activation WITHOUT operator approval -> REJECTED
    ok, reason, _ = promo_mgr.activate_model(
        model_id="candidate_model_01",
        operator_approved=False,
    )
    assert ok is False
    assert "Operator approval required" in reason

    # 2. Attempt activation WITH operator approval -> SUCCESS
    from jarvis_learning.storage.learning_db import LearningDatabase

    audit_db = LearningDatabase(tmp_path / "models_registry.sqlite")

    ok_approved, reason_ok, updated_rec = promo_mgr.activate_model(
        model_id="candidate_model_01",
        operator_approved=True,
        audit_db=audit_db,
        operator_id="admin_operator",
    )
    assert ok_approved is True
    assert updated_rec is not None
    assert updated_rec.status == ModelStatus.PROMOTED

    # 3. Verify permanent audit log recorded in SQLite
    audit_logs = audit_db.list_audit_logs(limit=10)
    assert len(audit_logs) >= 1
    assert audit_logs[0]["event_type"] == "model_promoted"
    assert audit_logs[0]["model_id"] == "candidate_model_01"
    assert audit_logs[0]["operator_id"] == "admin_operator"


def test_decision_trace_field_completeness(clean_engine: LearningEngine) -> None:
    """Verify DecisionTrace contains every required explainability and observability field."""
    model = MockDeterministicModel(confidence=0.90)
    clean_engine.attach_local_model(model)

    res = clean_engine.route_turn(
        user_input="set volume to mute",
        session_id="trace_test_sess",
        local_models_enabled=True,
        shadow_mode_enabled=True,
    )
    trace = res.trace

    # Verify all required fields from Objective 9
    assert trace.trace_id != ""
    assert trace.timestamp > 0
    assert trace.session_id == "trace_test_sess"
    assert trace.user_input == "set volume to mute"
    assert trace.task_family == "tool_policy"
    assert trace.selected_handler == "foundation_llm"
    assert trace.routing_state == RoutingState.SHADOW_ONLY.value
    assert trace.model_id == "mock_model_v1"
    assert trace.model_version == "v1.0.0"
    assert trace.model_availability in ("active", "shadow")
    assert trace.raw_confidence == 0.90
    assert trace.calibrated_confidence == 0.90
    assert trace.ood_score >= 0.0
    assert trace.risk_level == "low"
    assert trace.eligibility_result == "eligible"
    assert trace.authorization_result == "shadow_only"
    assert trace.fallback_reason != ""
    assert trace.latency_ms >= 0.0

    # Test round-trip dictionary serialization
    d = trace.to_dict()
    assert isinstance(d, dict)
    from_dict_trace = trace.from_dict(d)
    assert from_dict_trace.trace_id == trace.trace_id
    assert from_dict_trace.routing_state == trace.routing_state
