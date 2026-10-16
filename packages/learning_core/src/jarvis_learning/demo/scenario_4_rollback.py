"""jarvis_learning.demo.scenario_4_rollback — Classified degradation and full bundle rollback."""

from __future__ import annotations

from typing import Any

from jarvis_learning.experience import now_ms
from jarvis_learning.models.lifecycle import ModelStatus
from jarvis_learning.models.registry import ModelRecord, ModelRegistry
from jarvis_learning.routing.health import RuntimeHealthMonitor


def run_scenario_4_classified_rollback(db_path: str) -> dict[str, Any]:
    """Demonstrates automatic rollback on model drift and restart persistence."""
    registry = ModelRegistry(db_path=db_path)

    # 1. Active model candidate
    active_record = ModelRecord(
        model_id="local_transformer_v2",
        target="tool_policy",
        version="v2.0.0",
        architecture="nano_transformer",
        compute_tier="cpu",
        weights_path="/models/tool_policy/v2/weights.npz",
        weights_sha256="hash_v2_active",
        artifact_size=10240,
        dataset_manifest_hash="ds_hash_v2",
        parameters_count=25000,
        baseline_beaten="tfidf_baseline_v1",
        val_loss=0.04,
        val_metrics={"accuracy": 0.92},
        status=ModelStatus.PROMOTED,
        created_at=now_ms(),
    )
    registry.register(active_record)

    # 2. Baseline fallback entry
    baseline_record = ModelRecord(
        model_id="tfidf_baseline_v1",
        target="tool_policy",
        version="v1.0.0",
        architecture="tfidf_logistic",
        compute_tier="fallback",
        weights_path="/models/tool_policy/v1/weights.json",
        weights_sha256="hash_v1_baseline",
        artifact_size=5120,
        dataset_manifest_hash="ds_hash_v1",
        parameters_count=5000,
        baseline_beaten="frequency_baseline",
        val_loss=0.10,
        val_metrics={"accuracy": 0.85},
        status=ModelStatus.SHADOW,
        created_at=now_ms() - 10000,
    )
    registry.register(baseline_record)

    monitor = RuntimeHealthMonitor(window_size=10, max_consecutive_model_failures=3)

    # 3. Simulate 3 consecutive model drift execution failures
    health = None
    for i in range(3):
        health = monitor.record_execution(
            turn_id=f"turn_drift_{i}",
            tool_name="volume.mute",
            success=False,
            error_message="Model selected wrong arguments resulting in bad execution",
        )

    assert health is not None
    assert health.rollback_required is True
    assert "consecutive model-caused failures" in health.trigger_reason.lower()

    # 4. Perform atomic rollback
    registry.update_status(
        "local_transformer_v2", ModelStatus.ROLLED_BACK, reason="Model drift consecutive errors"
    )
    registry.update_status(
        "tfidf_baseline_v1", ModelStatus.PROMOTED, reason="Restored after candidate rollback"
    )

    # 5. Process restart verification: reload registry from disk
    restarted_registry = ModelRegistry(db_path=db_path)
    current_active = restarted_registry.get_active("tool_policy")
    assert current_active is not None
    assert current_active.model_id == "tfidf_baseline_v1"

    failed_model = restarted_registry.get("local_transformer_v2")
    assert failed_model is not None
    assert failed_model.status == ModelStatus.ROLLED_BACK

    return {
        "status": "passed",
        "rollback_triggered": True,
        "trigger_reason": health.trigger_reason,
        "active_after_restart": current_active.model_id,
        "failed_candidate_state": failed_model.status.value,
    }
