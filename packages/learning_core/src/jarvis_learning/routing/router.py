"""jarvis_learning.routing.router — hybrid model router and decision orchestrator."""

from __future__ import annotations

from enum import StrEnum
import logging
from pathlib import Path
import time
from dataclasses import dataclass
from typing import Any

from ..models.arguments import DeterministicArgumentBuilder
from ..models.base import LocalModel, ToolPrediction
from ..models.decision_trace import DecisionTrace
from ..models.registry import ModelRegistry
from ..strategies import StrategyStore
from .guard import LocalDecisionGuard
from .health import RuntimeHealthMonitor
from .ood import DistributionGuard
from .promotion import PromotionManager
from .shadow import ShadowExecutor, ShadowObservation

logger = logging.getLogger(__name__)


class RoutingState(StrEnum):
    """Explicit, closed routing states distinguishing exact router decisions."""

    NO_MODEL = "NO_MODEL"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_INCOMPATIBLE = "MODEL_INCOMPATIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OOD_ABSTAIN = "OOD_ABSTAIN"
    LOW_CONFIDENCE_ABSTAIN = "LOW_CONFIDENCE_ABSTAIN"
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"
    POLICY_DENIED = "POLICY_DENIED"
    SHADOW_ONLY = "SHADOW_ONLY"
    ADVISORY_ELIGIBLE = "ADVISORY_ELIGIBLE"
    PRODUCTION_ELIGIBLE = "PRODUCTION_ELIGIBLE"
    PRODUCTION_ACTIVE = "PRODUCTION_ACTIVE"
    ERROR_SAFE_FALLBACK = "ERROR_SAFE_FALLBACK"


@dataclass(frozen=True, slots=True)
class RouterConfig:
    """Configuration governing model routing and autonomy."""

    local_models_enabled: bool = False  # Disabled by default
    shadow_mode_enabled: bool = True  # Shadow evaluation active
    automatic_promotion_enabled: bool = False  # Operator confirmation required
    automatic_rollback_enabled: bool = True  # Auto-rollback on health failure
    min_calibrated_confidence: float = 0.85
    ood_threshold: float = 0.5
    require_calibration: bool = False


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Outcome of router decision."""

    handler: str  # "strategy_store" | "local_model" | "foundation_llm"
    tool_name: str
    tool_arguments: dict[str, Any]
    trace: DecisionTrace
    routing_state: RoutingState
    confidence: float = 0.0
    task_continuity_applied: bool = False
    model_prediction: ToolPrediction | None = None


class ModelRouter:
    """Orchestrates hybrid decision routing across multiple decision layers with strict safety gating."""

    def __init__(
        self,
        config: RouterConfig | None = None,
        strategy_store: StrategyStore | None = None,
        registry: ModelRegistry | None = None,
    ) -> None:
        self.config = config or RouterConfig()
        self.strategy_store = strategy_store or StrategyStore()
        self.registry = registry or ModelRegistry()

        self.guard = LocalDecisionGuard(
            min_calibrated_confidence=self.config.min_calibrated_confidence
        )
        self.ood_guard = DistributionGuard(ood_threshold=self.config.ood_threshold)
        self.arg_builder = DeterministicArgumentBuilder()
        self.health_monitor = RuntimeHealthMonitor()
        self.shadow_executor = ShadowExecutor()
        self.promotion_manager = PromotionManager(
            registry=self.registry,
            allow_automatic_promotion=self.config.automatic_promotion_enabled,
            allow_automatic_rollback=self.config.automatic_rollback_enabled,
        )

        self._active_local_model: LocalModel | None = None
        self._baseline_model: LocalModel | None = None
        self._candidate_models: dict[str, LocalModel] = {}

    def set_active_model(self, model: LocalModel) -> None:
        """Attach the currently active production/shadow local model."""
        self._active_local_model = model

    def set_baseline_model(self, model: LocalModel) -> None:
        """Attach fallback baseline model (e.g. TF-IDF)."""
        self._baseline_model = model

    def register_candidate_model(self, model: LocalModel) -> None:
        """Register candidate model for shadow evaluation."""
        self._candidate_models[model.model_id] = model

    def resolve_active_model(self, target: str = "tool_policy") -> tuple[LocalModel | None, str]:
        """Discover and resolve the appropriate model based on registry and runtime attachments."""
        # 1. Explicitly set active model has first precedence
        if self._active_local_model is not None and self._active_local_model.is_loaded:
            return self._active_local_model, "active"

        # 2. Check SQLite registry for promoted model
        promoted_rec = self.registry.get_active_model(target)
        if promoted_rec:
            # Check candidate models cache
            if promoted_rec.model_id in self._candidate_models:
                cand = self._candidate_models[promoted_rec.model_id]
                if cand.is_loaded:
                    self._active_local_model = cand
                    return cand, "promoted_registry"
            # Try to load artifact if file exists
            if promoted_rec.weights_path and Path(promoted_rec.weights_path).exists():
                try:
                    from ..transformer.runtime_adapter import TransformerToolPolicyModel

                    model = TransformerToolPolicyModel(
                        model_id=promoted_rec.model_id, version=promoted_rec.version
                    )
                    model.load(Path(promoted_rec.weights_path))
                    self._active_local_model = model
                    return model, "loaded_registry"
                except Exception as e:
                    logger.warning(
                        "Failed to load promoted model from %s: %s", promoted_rec.weights_path, e
                    )

        # 3. Fallback to attached baseline model
        if self._baseline_model is not None and self._baseline_model.is_loaded:
            return self._baseline_model, "baseline"

        # 4. If active model is set but not loaded
        if self._active_local_model is not None:
            return self._active_local_model, "unloaded"

        return None, "none"

    def route(
        self,
        *,
        user_input: str,
        session_id: str = "sess_001",
        context: dict[str, Any] | None = None,
        task_family: str = "tool_policy",
    ) -> RoutingResult:
        """Determines execution path following the 17-step safety-first routing logic."""
        context = context or {}
        start_time = time.perf_counter()

        # Step 1: Input normalization
        norm_input = user_input.strip()

        # Step 2: Task continuity check
        active_target_id = context.get("active_browser_target_id") or context.get("active_app_id")
        task_stage = context.get("task_stage")
        is_continuity = bool(active_target_id and task_stage)

        # Step 3: Preliminary risk classification
        lower_input = norm_input.lower()
        is_high_risk = any(
            kw in lower_input
            for kw in ("rm -rf", "delete file", "drop database", "format drive", "mkfs", "dd if=")
        )
        if is_high_risk:
            # High risk tasks CANNOT be routed to local models under any circumstances
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.POLICY_DENIED.value,
                task_family=task_family,
                guard_decision="blocked_high_risk",
                fallback_reason="Preliminary risk classification blocked destructive local execution",
                policy_result="blocked_destructive",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.POLICY_DENIED,
                confidence=0.0,
            )

        # Step 4: Check Proven Strategy Store (with active status & decay checks)
        strategies = self.strategy_store.find_strategies_for_intent(norm_input)
        if strategies and strategies[0].confidence >= 0.80:
            strat = strategies[0]

            # Step 5: Check relevant failure patterns
            patterns = self.strategy_store.find_failure_patterns_for_action(
                strat.tool, strat.argument_pattern
            )
            if not patterns:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                trace = DecisionTrace.create(
                    session_id=session_id,
                    user_input=norm_input,
                    selected_handler="strategy_store",
                    routing_state=RoutingState.PRODUCTION_ACTIVE.value,
                    task_family=task_family,
                    tool_predicted=strat.tool,
                    tool_executed=strat.tool,
                    calibrated_confidence=strat.confidence,
                    eligibility_result="eligible",
                    authorization_result="authorized",
                    latency_ms=round(latency_ms, 2),
                    metadata={"strategy_id": strat.id},
                )
                args = dict(strat.argument_pattern)
                if is_continuity and active_target_id:
                    args["target_id"] = active_target_id

                return RoutingResult(
                    handler="strategy_store",
                    tool_name=strat.tool,
                    tool_arguments=args,
                    trace=trace,
                    routing_state=RoutingState.PRODUCTION_ACTIVE,
                    confidence=strat.confidence,
                    task_continuity_applied=is_continuity,
                )

        # Step 6: Check local model enablement
        if not self.config.local_models_enabled:
            # Shadow evaluation when disabled by configuration
            model, model_role = self.resolve_active_model(target=task_family)
            predicted_tool_name = ""
            cal_conf = 0.0
            pred_obj = None

            if model is not None and model.is_loaded and self.config.shadow_mode_enabled:
                try:
                    pred_obj = model.predict({"user_input": norm_input})
                    if isinstance(pred_obj, ToolPrediction) and pred_obj.is_finite:
                        predicted_tool_name = pred_obj.tool_name
                        cal_conf = pred_obj.calibrated_confidence
                        self.shadow_executor.record_observation(
                            ShadowObservation(
                                session_id=session_id,
                                model_id=model.model_id,
                                predicted_tool=predicted_tool_name,
                                predicted_confidence=cal_conf,
                                active_tool="foundation_llm",
                                verified_successful_tool="",
                                is_agreement=False,
                                is_verified_correct=False,
                                latency_ms=0.0,
                                category=task_family,
                            )
                        )
                except Exception:
                    pass

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.SHADOW_ONLY.value
                if self.config.shadow_mode_enabled
                else RoutingState.NO_MODEL.value,
                task_family=task_family,
                model_id=model.model_id if model else "",
                model_version=model.version if model else "",
                model_availability=model_role if model else "none",
                tool_predicted=predicted_tool_name,
                calibrated_confidence=cal_conf,
                raw_confidence=cal_conf,
                fallback_reason="Local models disabled by configuration",
                eligibility_result="eligible" if predicted_tool_name else "ineligible",
                authorization_result="shadow_only" if self.config.shadow_mode_enabled else "denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.SHADOW_ONLY
                if self.config.shadow_mode_enabled
                else RoutingState.NO_MODEL,
                confidence=cal_conf,
                task_continuity_applied=is_continuity,
                model_prediction=pred_obj,
            )

        # Step 7: Model discovery and resolution
        model, model_role = self.resolve_active_model(target=task_family)
        if model is None:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.NO_MODEL.value,
                task_family=task_family,
                model_availability="none",
                fallback_reason="No local model configured or registered",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.NO_MODEL,
                confidence=0.0,
            )

        if not model.is_loaded:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.MODEL_UNAVAILABLE.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                model_availability="unavailable",
                fallback_reason="Model artifact not loaded into memory",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.MODEL_UNAVAILABLE,
                confidence=0.0,
            )

        # Step 8: Compatibility check
        if model.target != task_family:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.MODEL_INCOMPATIBLE.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                model_availability="incompatible",
                fallback_reason=f"Model target '{model.target}' incompatible with requested '{task_family}'",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.MODEL_INCOMPATIBLE,
                confidence=0.0,
            )

        # Step 9: OOD evaluation
        ood = self.ood_guard.evaluate(norm_input, task_family=task_family)
        if ood.is_ood:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.OOD_ABSTAIN.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                model_availability=model_role,
                ood_score=ood.score,
                guard_decision="blocked_ood",
                eligibility_result="abstained",
                fallback_reason=f"Out of distribution query ({ood.reason})",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.OOD_ABSTAIN,
                confidence=0.0,
            )

        # Step 10: Safe model prediction execution
        try:
            prediction = model.predict({"user_input": norm_input})
        except Exception as e:
            logger.exception("Inference error in model %s: %s", model.model_id, e)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.ERROR_SAFE_FALLBACK.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                fallback_reason=f"Inference exception: {e}",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.ERROR_SAFE_FALLBACK,
                confidence=0.0,
            )

        if (
            not isinstance(prediction, ToolPrediction)
            or not prediction.is_finite
            or not prediction.tool_name
        ):
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.LOW_CONFIDENCE_ABSTAIN.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                fallback_reason="Model abstained or returned non-finite/empty prediction",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.LOW_CONFIDENCE_ABSTAIN,
                confidence=0.0,
            )

        # Step 11: Calibration check
        if self.config.require_calibration and hasattr(model, "calibrator"):
            calibrator = getattr(model, "calibrator")
            if not getattr(calibrator, "is_calibrated", True):
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                trace = DecisionTrace.create(
                    session_id=session_id,
                    user_input=norm_input,
                    selected_handler="foundation_llm",
                    routing_state=RoutingState.CALIBRATION_UNAVAILABLE.value,
                    task_family=task_family,
                    model_id=model.model_id,
                    model_version=model.version,
                    calibration_state="unavailable",
                    fallback_reason="Calibration metrics unavailable or stale for required threshold",
                    authorization_result="denied",
                    latency_ms=round(latency_ms, 2),
                )
                return RoutingResult(
                    handler="foundation_llm",
                    tool_name="",
                    tool_arguments={},
                    trace=trace,
                    routing_state=RoutingState.CALIBRATION_UNAVAILABLE,
                    confidence=prediction.raw_confidence,
                    model_prediction=prediction,
                )

        # Step 12: Decision Guard policy check
        guard_decision = self.guard.validate(prediction, context)
        if not guard_decision.allowed:
            state = (
                RoutingState.POLICY_DENIED
                if guard_decision.risk_level in ("destructive", "high", "medium")
                or "not in approved" in guard_decision.reason
                else RoutingState.LOW_CONFIDENCE_ABSTAIN
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=state.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                raw_confidence=prediction.raw_confidence,
                calibrated_confidence=prediction.calibrated_confidence,
                ood_score=ood.score,
                risk_level=prediction.risk_level,
                guard_decision=guard_decision.reason,
                policy_result="blocked_" + guard_decision.risk_level,
                fallback_reason=f"Decision guard blocked execution ({guard_decision.reason})",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=state,
                confidence=prediction.calibrated_confidence,
                model_prediction=prediction,
            )

        # Step 13: Deterministic Argument Builder & schema validation
        arg_result = self.arg_builder.build_arguments(prediction.tool_name, norm_input, context)
        if not arg_result.success:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.ADVISORY_ELIGIBLE.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                tool_predicted=prediction.tool_name,
                raw_confidence=prediction.raw_confidence,
                calibrated_confidence=prediction.calibrated_confidence,
                ood_score=ood.score,
                risk_level=prediction.risk_level,
                eligibility_result="eligible",
                authorization_result="denied",
                fallback_reason=f"Argument synthesis required reasoning ({arg_result.reason})",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.ADVISORY_ELIGIBLE,
                confidence=prediction.calibrated_confidence,
                model_prediction=prediction,
            )

        # Step 14: Failure pattern check
        fail_patterns = self.strategy_store.find_failure_patterns_for_action(
            prediction.tool_name, arg_result.arguments
        )
        if fail_patterns:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.POLICY_DENIED.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                tool_predicted=prediction.tool_name,
                fallback_reason="Blocked by active failure pattern",
                authorization_result="denied",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.POLICY_DENIED,
                confidence=prediction.calibrated_confidence,
                model_prediction=prediction,
            )

        # Step 15: Execution or Shadow evaluation
        out_args = dict(arg_result.arguments)
        if is_continuity and active_target_id:
            out_args["target_id"] = active_target_id

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if self.config.shadow_mode_enabled:
            # Model is qualified/eligible, but router is operating in shadow mode
            self.shadow_executor.record_observation(
                ShadowObservation(
                    session_id=session_id,
                    model_id=model.model_id,
                    predicted_tool=prediction.tool_name,
                    predicted_confidence=prediction.calibrated_confidence,
                    active_tool="foundation_llm",
                    verified_successful_tool="",
                    is_agreement=False,
                    is_verified_correct=False,
                    latency_ms=round(latency_ms, 2),
                    category=task_family,
                )
            )
            trace = DecisionTrace.create(
                session_id=session_id,
                user_input=norm_input,
                selected_handler="foundation_llm",
                routing_state=RoutingState.SHADOW_ONLY.value,
                task_family=task_family,
                model_id=model.model_id,
                model_version=model.version,
                model_availability=model_role,
                raw_confidence=prediction.raw_confidence,
                calibrated_confidence=prediction.calibrated_confidence,
                ood_score=ood.score,
                risk_level=prediction.risk_level,
                guard_decision="allowed",
                eligibility_result="eligible",
                authorization_result="shadow_only",
                tool_predicted=prediction.tool_name,
                fallback_reason="Shadow mode active; routing execution to foundation LLM",
                latency_ms=round(latency_ms, 2),
            )
            return RoutingResult(
                handler="foundation_llm",
                tool_name="",
                tool_arguments={},
                trace=trace,
                routing_state=RoutingState.SHADOW_ONLY,
                confidence=prediction.calibrated_confidence,
                task_continuity_applied=is_continuity,
                model_prediction=prediction,
            )

        # Active production path
        trace = DecisionTrace.create(
            session_id=session_id,
            user_input=norm_input,
            selected_handler="local_model",
            routing_state=RoutingState.PRODUCTION_ACTIVE.value,
            task_family=task_family,
            model_id=model.model_id,
            model_version=model.version,
            model_availability=model_role,
            raw_confidence=prediction.raw_confidence,
            calibrated_confidence=prediction.calibrated_confidence,
            ood_score=ood.score,
            risk_level=prediction.risk_level,
            guard_decision="allowed",
            eligibility_result="eligible",
            authorization_result="authorized",
            tool_predicted=prediction.tool_name,
            tool_executed=prediction.tool_name,
            latency_ms=round(latency_ms, 2),
        )

        return RoutingResult(
            handler="local_model",
            tool_name=prediction.tool_name,
            tool_arguments=out_args,
            trace=trace,
            routing_state=RoutingState.PRODUCTION_ACTIVE,
            confidence=prediction.calibrated_confidence,
            task_continuity_applied=is_continuity,
            model_prediction=prediction,
        )
