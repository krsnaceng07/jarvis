"""jarvis_learning.demo.scenario_3_shadow_promo — Multi-metric shadow qualification and operator gate."""

from __future__ import annotations

from typing import Any

from jarvis_learning.experience import now_ms
from jarvis_learning.models.lifecycle import ModelStatus
from jarvis_learning.models.registry import ModelRecord, ModelRegistry
from jarvis_learning.routing.promotion import PromotionManager
from jarvis_learning.routing.shadow import ShadowExecutor, ShadowObservation


def run_scenario_3_shadow_qualification(db_path: str) -> dict[str, Any]:
    """Demonstrates multi-dimensional shadow qualification without automatic activation."""
    registry = ModelRegistry(db_path=db_path)
    record = ModelRecord(
        model_id="nano_transformer_candidate_v1",
        target="tool_policy",
        version="v1.0.0",
        architecture="nano_transformer",
        compute_tier="cpu",
        weights_path="/models/tool_policy/v1/weights.npz",
        weights_sha256="abc1234567890",
        artifact_size=10240,
        dataset_manifest_hash="ds_hash_123",
        parameters_count=25000,
        baseline_beaten="tfidf_baseline_v1",
        val_loss=0.05,
        val_metrics={"accuracy": 0.90},
        status=ModelStatus.SHADOW,
        created_at=now_ms(),
    )
    registry.register(record)

    executor = ShadowExecutor()
    categories = ["browser", "system", "media", "files"]

    # Record 50 shadow observations across all 4 categories with 90% verified accuracy
    for i in range(50):
        cat = categories[i % len(categories)]
        tool = f"{cat}.action_{i % 3}"
        predicted = tool if i % 10 != 0 else f"{cat}.fallback"
        obs = ShadowObservation(
            session_id=f"sess_shadow_{i}",
            model_id="nano_transformer_candidate_v1",
            predicted_tool=predicted,
            predicted_confidence=0.92,
            active_tool=predicted,
            verified_successful_tool=tool,
            is_agreement=True,
            is_verified_correct=(predicted == tool),
            latency_ms=12.5,
            category=cat,
        )
        executor.record_observation(obs)

    promo = PromotionManager(
        registry=registry,
        allow_automatic_promotion=False,  # Operator gate strictly enforced
    )

    eval_result = promo.evaluate_candidate("nano_transformer_candidate_v1", executor)
    assert eval_result.qualifies is True, (
        "Candidate with 90% accuracy across 4 categories failed qualification"
    )

    # Verify that model was NOT automatically activated
    candidate_after = registry.get("nano_transformer_candidate_v1")
    assert candidate_after is not None
    assert candidate_after.status == ModelStatus.SHADOW, (
        "Model was illegally auto-promoted without operator approval!"
    )

    # Now simulate explicit operator approval command
    promo.promote("nano_transformer_candidate_v1", operator_approved=True)
    candidate_promoted = registry.get("nano_transformer_candidate_v1")
    assert candidate_promoted is not None
    assert candidate_promoted.status == ModelStatus.PROMOTED

    return {
        "status": "passed",
        "qualified": eval_result.qualifies,
        "sample_count": eval_result.sample_count,
        "accuracy": eval_result.accuracy,
        "categories_covered": list(eval_result.category_accuracies.keys()),
        "auto_promotion_blocked": True,
        "operator_approval_respected": True,
    }
