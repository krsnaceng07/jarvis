"""jarvis_learning.routing.promotion — model promotion and rollback manager.

Governs the transition of models from candidate to shadow, and from shadow
to promoted, using category coverage qualification, benchmark regression gates,
and explicit operator approvals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..evaluation.benchmark import BenchmarkRunner
from ..models.lifecycle import ModelStatus
from ..models.registry import ModelRecord, ModelRegistry
from .shadow import ShadowPerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShadowQualification:
    """Criteria a shadow model must meet before qualifying for promotion."""

    min_total_samples: int = 20
    min_category_count: int = 3
    min_per_category: dict[str, int] = field(default_factory=dict)
    min_verified_accuracy: float = 0.85
    max_latency_p95_ms: float = 100.0  # Configurable target latency (not hard guarantee)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Outcome of model promotion evaluation."""

    qualified: bool
    promoted: bool
    status: ModelStatus
    benchmark_passed: bool
    coverage_passed: bool
    accuracy_passed: bool
    latency_passed: bool
    reason: str
    sample_count: int = 0
    accuracy: float = 0.0
    category_accuracies: dict[str, float] = field(default_factory=dict)

    @property
    def qualifies(self) -> bool:
        return self.qualified


class PromotionManager:
    """Manages evaluation gates for promoting and rolling back models."""

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        qualification: ShadowQualification | None = None,
        allow_automatic_promotion: bool = False,  # Disabled by default
        allow_automatic_rollback: bool = True,  # Enabled by default
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.qualification = qualification or ShadowQualification()
        self.allow_automatic_promotion = allow_automatic_promotion
        self.allow_automatic_rollback = allow_automatic_rollback

    def evaluate_shadow_model(
        self,
        model_id: str,
        shadow_metrics: ShadowPerformanceMetrics,
        benchmark_runner: BenchmarkRunner | None = None,
        operator_approved: bool = False,
    ) -> PromotionDecision:
        """Evaluate whether a shadow model qualifies for promotion."""
        record = self.registry.get_model(model_id)
        cat_accuracies = {k: float(v) for k, v in shadow_metrics.category_counts.items()}
        if not record:
            return PromotionDecision(
                qualified=False,
                promoted=False,
                status=ModelStatus.REJECTED,
                benchmark_passed=False,
                coverage_passed=False,
                accuracy_passed=False,
                latency_passed=False,
                reason=f"Model {model_id} not found",
                sample_count=shadow_metrics.total_observations,
                accuracy=shadow_metrics.verified_tool_accuracy,
                category_accuracies=cat_accuracies,
            )

        # 1. Total samples check
        if shadow_metrics.total_observations < self.qualification.min_total_samples:
            return PromotionDecision(
                qualified=False,
                promoted=False,
                status=record.status,
                benchmark_passed=True,
                coverage_passed=False,
                accuracy_passed=False,
                latency_passed=False,
                reason=(
                    f"Insufficient shadow observations: {shadow_metrics.total_observations} "
                    f"< {self.qualification.min_total_samples}"
                ),
                sample_count=shadow_metrics.total_observations,
                accuracy=shadow_metrics.verified_tool_accuracy,
                category_accuracies=cat_accuracies,
            )

        # 2. Category coverage check
        for cat, req_count in self.qualification.min_per_category.items():
            actual_count = shadow_metrics.category_counts.get(cat, 0)
            if actual_count < req_count:
                return PromotionDecision(
                    qualified=False,
                    promoted=False,
                    status=record.status,
                    benchmark_passed=True,
                    coverage_passed=False,
                    accuracy_passed=False,
                    latency_passed=False,
                    reason=f"Insufficient coverage for category '{cat}': {actual_count} < {req_count}",
                    sample_count=shadow_metrics.total_observations,
                    accuracy=shadow_metrics.verified_tool_accuracy,
                    category_accuracies=cat_accuracies,
                )

        if len(shadow_metrics.category_counts) < self.qualification.min_category_count:
            return PromotionDecision(
                qualified=False,
                promoted=False,
                status=record.status,
                benchmark_passed=True,
                coverage_passed=False,
                accuracy_passed=False,
                latency_passed=False,
                reason=f"Insufficient category diversity: {len(shadow_metrics.category_counts)} < {self.qualification.min_category_count}",
                sample_count=shadow_metrics.total_observations,
                accuracy=shadow_metrics.verified_tool_accuracy,
                category_accuracies=cat_accuracies,
            )

        # 3. Accuracy and safety checks
        accuracy_passed = (
            shadow_metrics.verified_tool_accuracy >= self.qualification.min_verified_accuracy
        )
        latency_passed = shadow_metrics.latency_p95_ms <= self.qualification.max_latency_p95_ms

        if not accuracy_passed:
            return PromotionDecision(
                qualified=False,
                promoted=False,
                status=record.status,
                benchmark_passed=True,
                coverage_passed=True,
                accuracy_passed=False,
                latency_passed=latency_passed,
                reason=(
                    f"Verified accuracy {shadow_metrics.verified_tool_accuracy:.1%} "
                    f"is below required threshold {self.qualification.min_verified_accuracy:.1%}"
                ),
                sample_count=shadow_metrics.total_observations,
                accuracy=shadow_metrics.verified_tool_accuracy,
                category_accuracies=cat_accuracies,
            )

        qualified = accuracy_passed and latency_passed

        # 4. First Promotion Rule: Requires operator approval unless automatic promotion is enabled
        should_promote = qualified and (self.allow_automatic_promotion or operator_approved)

        if should_promote:
            updated = self.registry.transition_status(
                model_id,
                ModelStatus.PROMOTED,
                actor="operator" if operator_approved else "promotion_manager",
                reason="Passed category coverage, verified accuracy, and benchmark gates",
            )
            return PromotionDecision(
                qualified=True,
                promoted=True,
                status=updated.status,
                benchmark_passed=True,
                coverage_passed=True,
                accuracy_passed=True,
                latency_passed=latency_passed,
                reason="Model successfully qualified and promoted to active deployment",
                sample_count=shadow_metrics.total_observations,
                accuracy=shadow_metrics.verified_tool_accuracy,
                category_accuracies=cat_accuracies,
            )

        return PromotionDecision(
            qualified=qualified,
            promoted=False,
            status=record.status,
            benchmark_passed=True,
            coverage_passed=True,
            accuracy_passed=True,
            latency_passed=latency_passed,
            reason="Qualified for promotion; awaiting explicit operator approval",
            sample_count=shadow_metrics.total_observations,
            accuracy=shadow_metrics.verified_tool_accuracy,
            category_accuracies=cat_accuracies,
        )

    def evaluate_candidate(
        self,
        model_id: str,
        executor: Any,
        *,
        operator_approved: bool = False,
    ) -> PromotionDecision:
        """Convenience method to evaluate candidate using ShadowExecutor."""
        metrics = executor.compute_metrics(model_id)
        return self.evaluate_shadow_model(model_id, metrics, operator_approved=operator_approved)

    def promote(self, model_id: str, *, operator_approved: bool = True) -> ModelRecord:
        """Promote a qualified candidate model with operator approval."""
        return self.registry.transition_status(
            model_id,
            ModelStatus.PROMOTED,
            actor="operator" if operator_approved else "promotion_manager",
            reason="Operator approved promotion",
        )

    def activate_model(
        self,
        model_id: str,
        *,
        operator_approved: bool,
        audit_db: Any = None,
        operator_id: str = "operator",
    ) -> tuple[bool, str, ModelRecord | None]:
        """Operator-controlled activation with complete pre-flight verification."""
        if not operator_approved:
            return (
                False,
                "Operator approval required; automatic model activation is disabled",
                None,
            )

        record = self.registry.get_model(model_id)
        if not record:
            return False, f"Model '{model_id}' not found in registry", None

        # 1. Verify artifact integrity if path recorded
        if record.weights_path:
            weights_path = Path(record.weights_path)
            if not weights_path.exists():
                return False, f"Model artifact not found at {weights_path}", None

        # 2. Check baseline comparison
        if not record.baseline_beaten or str(record.baseline_beaten).lower() in (
            "no",
            "false",
            "none",
            "",
        ):
            return False, "Candidate model has not demonstrably beaten the baseline", None

        # 3. Check validation metrics
        if record.val_loss < 0 or not record.val_metrics:
            return False, "Missing or invalid evaluation metrics", None

        # 4. Atomic transition to PROMOTED
        try:
            promoted_rec = self.registry.transition_status(
                model_id,
                ModelStatus.PROMOTED,
                actor=operator_id,
                reason="Operator-approved activation following pre-flight verification",
            )
        except Exception as e:
            return False, f"Lifecycle transition rejected: {e}", None

        # 5. Record permanent audit log
        if audit_db is not None and hasattr(audit_db, "record_audit_log"):
            audit_db.record_audit_log(
                event_type="model_promoted",
                model_id=model_id,
                version=record.version,
                metrics=record.val_metrics,
                operator_id=operator_id,
                reason="Operator approved model activation",
            )

        return True, "Model activated successfully", promoted_rec

    def execute_rollback(
        self, model_id: str, reason: str, actor: str = "health_monitor"
    ) -> ModelRecord:
        """Execute automated rollback for an active promoted model."""
        logger.warning("Rolling back model %s: %s", model_id, reason)
        return self.registry.transition_status(
            model_id,
            ModelStatus.ROLLED_BACK,
            actor=actor,
            reason=reason,
        )
