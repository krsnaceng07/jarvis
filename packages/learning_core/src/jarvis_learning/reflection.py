"""jarvis_learning.reflection — post-task reflection and learning critic.

The ``ReflectionEngine`` analyzes completed experiences to extract
generalizable lessons.  The ``LearningCritic`` evaluates whether
a task was truly successful, looking for false claims, redundant
steps, missed context, and suboptimal tool choices.

Reflection only runs on experiences that exceed a configurable
complexity threshold — trivial interactions are stored but not
reflected on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .causal_critic import CausalCritic, CausalFailureType
from .confidence_engine import BayesianConfidenceState
from .experience import Experience, Lesson, generate_id, now_ms
from .feedback_attribution import FeedbackAttributor
from .path_quality import PathQualityEvaluator
from .precondition_contract import PreconditionContract
from .strategies import ScopeLevel, StrategyStore
from .verification import CompositeVerifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CritiqueCheck:
    """One check performed by the learning critic."""

    check_name: str
    passed: bool
    detail: str = ""
    severity: str = "info"  # info, warning, critical


@dataclass(frozen=True, slots=True)
class CritiqueResult:
    """Full critique of an experience."""

    experience_id: str
    checks: tuple[CritiqueCheck, ...] = ()
    overall_quality: float = 0.5
    lesson_summary: str = ""
    should_create_strategy: bool = False
    should_create_failure_pattern: bool = False

    @property
    def passed_all(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def critical_failures(self) -> list[CritiqueCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "critical"]


class LearningCritic:
    """Post-action critic that evaluates experience quality.

    Checks:
    1. Did the tool result match the claimed outcome?
    2. Were there unnecessary/redundant steps?
    3. Did the task actually succeed?
    4. Were there false completion claims?
    """

    def __init__(self) -> None:
        self._verifier = CompositeVerifier()

    def critique(self, experience: Experience) -> CritiqueResult:
        """Analyze an experience for quality and extract insights."""
        checks: list[CritiqueCheck] = []

        # 1. Verification check
        verification = self._check_verification(experience)
        checks.append(verification)

        # 2. Redundancy check
        redundancy = self._check_redundancy(experience)
        checks.append(redundancy)

        # 3. Tool outcome consistency
        consistency = self._check_tool_consistency(experience)
        checks.append(consistency)

        # 4. False claim detection
        false_claim = self._check_false_claims(experience)
        checks.append(false_claim)

        # Compute overall quality
        passed = sum(1 for c in checks if c.passed)
        quality = passed / len(checks) if checks else 0.5

        # Decide if this merits a strategy or failure pattern
        should_strategy = experience.success and quality >= 0.7 and experience.selected_tool
        should_failure = not experience.success and any(
            c.severity == "critical" and not c.passed for c in checks
        )

        # Build lesson summary
        lesson_parts: list[str] = []
        for check in checks:
            if not check.passed:
                lesson_parts.append(f"{check.check_name}: {check.detail}")

        lesson_summary = "; ".join(lesson_parts) if lesson_parts else ""
        if experience.success and not lesson_parts:
            lesson_summary = (
                f"Successful use of {experience.selected_tool} "
                f"for intent: {experience.interpreted_intent}"
            )

        return CritiqueResult(
            experience_id=experience.id,
            checks=tuple(checks),
            overall_quality=quality,
            lesson_summary=lesson_summary,
            should_create_strategy=should_strategy,
            should_create_failure_pattern=should_failure,
        )

    def _check_verification(self, exp: Experience) -> CritiqueCheck:
        """Check if the experience outcome was verified."""
        if exp.verification_status == "verified_success":
            return CritiqueCheck(
                check_name="outcome_verification",
                passed=True,
                detail="outcome verified as success",
            )
        if exp.verification_status == "false_claim":
            return CritiqueCheck(
                check_name="outcome_verification",
                passed=False,
                detail="false completion claim detected",
                severity="critical",
            )
        if exp.verification_status == "verified_failure":
            return CritiqueCheck(
                check_name="outcome_verification",
                passed=False,
                detail="tool execution verified as failure",
                severity="warning",
            )
        return CritiqueCheck(
            check_name="outcome_verification",
            passed=True,
            detail="outcome unverified — no strong signal",
        )

    def _check_redundancy(self, exp: Experience) -> CritiqueCheck:
        """Check for unnecessary steps in the episode."""
        if exp.episode is None:
            return CritiqueCheck(
                check_name="step_redundancy",
                passed=True,
                detail="single-step task — no redundancy check needed",
            )
        unnecessary = exp.episode.unnecessary_steps
        if unnecessary > 0:
            return CritiqueCheck(
                check_name="step_redundancy",
                passed=False,
                detail=f"{unnecessary} unnecessary step(s) detected",
                severity="warning",
            )
        return CritiqueCheck(
            check_name="step_redundancy",
            passed=True,
            detail=f"all {exp.episode.total_steps} steps contributed",
        )

    def _check_tool_consistency(self, exp: Experience) -> CritiqueCheck:
        """Check if the tool result is consistent with the claimed success."""
        if not exp.selected_tool:
            return CritiqueCheck(
                check_name="tool_consistency",
                passed=True,
                detail="no tool used — skipping",
            )
        # If the experience claims success but has a failure_type, that's
        # inconsistent
        if exp.success and exp.failure_type:
            return CritiqueCheck(
                check_name="tool_consistency",
                passed=False,
                detail=(f"marked as success but has failure_type={exp.failure_type}"),
                severity="critical",
            )
        if not exp.success and not exp.failure_type and not exp.error:
            return CritiqueCheck(
                check_name="tool_consistency",
                passed=False,
                detail="marked as failure but no failure_type or error recorded",
                severity="warning",
            )
        return CritiqueCheck(
            check_name="tool_consistency",
            passed=True,
            detail="success/failure consistent with metadata",
        )

    def _check_false_claims(self, exp: Experience) -> CritiqueCheck:
        """Check if the LLM made false claims about the result."""
        if exp.verification_status == "false_claim":
            return CritiqueCheck(
                check_name="false_claim_detection",
                passed=False,
                detail="LLM claimed action completed but tool result contradicts",
                severity="critical",
            )
        return CritiqueCheck(
            check_name="false_claim_detection",
            passed=True,
            detail="no false claims detected",
        )


class ReflectionEngine:
    """Orchestrates post-task reflection to extract lessons.

    Only reflects on experiences above a complexity threshold.
    Uses the ``LearningCritic`` for analysis and produces
    ``Lesson`` and optionally ``Strategy`` / ``FailurePattern``
    objects.
    """

    def __init__(
        self,
        strategy_store: StrategyStore,
        *,
        min_complexity: float = 0.3,
    ) -> None:
        self._strategy_store = strategy_store
        self._critic = LearningCritic()
        self._causal_critic = CausalCritic()
        self._path_quality_evaluator = PathQualityEvaluator()
        self._min_complexity = min_complexity
        self._lessons: list[Lesson] = []

    def should_reflect(self, experience: Experience) -> bool:
        """Decide whether an experience merits reflection.

        Always reflect on: failures, user corrections, multi-step tasks.
        Skip trivially simple successful single-tool interactions.
        """
        if not experience.success:
            return True
        if experience.user_feedback in ("correction", "user_correction", "incorrect"):
            return True
        if experience.verification_status == "false_claim":
            return True
        if experience.episode and experience.episode.total_steps > 1:
            return True
        # Estimate complexity from field lengths as a proxy
        complexity_score = self._estimate_complexity(experience)
        return complexity_score >= self._min_complexity

    def reflect(self, experience: Experience) -> Lesson | None:
        """Run reflection on an experience and extract a lesson.

        Returns a ``Lesson`` if the reflection produced actionable
        insight, or ``None`` if the experience was too trivial.
        """
        if not self.should_reflect(experience):
            logger.debug(
                "skipping reflection for trivial experience: %s",
                experience.id,
            )
            return None

        critique = self._critic.critique(experience)
        logger.info(
            "reflection on %s: quality=%.2f checks=%d/%d",
            experience.id,
            critique.overall_quality,
            sum(1 for c in critique.checks if c.passed),
            len(critique.checks),
        )

        tool_args = self._safe_parse_json(experience.tool_arguments)

        # 1. Path Quality Evaluation & Strategy Creation for Successes
        if experience.success:
            success_quality, path_eval, strategy_worthy = self._path_quality_evaluator.evaluate(
                goal_satisfied=experience.verification_status == "verified_success"
                or experience.success,
                correct_target=True,
                duplicate_free=True,
                side_effects_clean=True,
                policy_compliant=True,
                actual_steps=1 if not experience.episode else experience.episode.total_steps,
                optimal_steps=1,
                execution_time_ms=100.0,
            )

            if critique.should_create_strategy and strategy_worthy and experience.selected_tool:
                # Risk tier assignment
                tool_lower = experience.selected_tool.lower()
                if any(k in tool_lower for k in ("kill", "terminate", "delete", "rm", "format")):
                    risk_tier = 4
                elif any(k in tool_lower for k in ("browser", "web", "http", "fetch", "navigate")):
                    risk_tier = 3
                elif any(k in tool_lower for k in ("write", "create", "edit", "save")):
                    risk_tier = 2
                else:
                    risk_tier = 1

                precond = PreconditionContract(
                    required_tools=[experience.selected_tool],
                )
                bayes_state = BayesianConfidenceState()
                bayes_state.update(success=True)

                self._strategy_store.create_strategy_from_experience(
                    intent=experience.interpreted_intent or experience.user_input[:100],
                    tool=experience.selected_tool,
                    argument_pattern=tool_args,
                    preferred_action=experience.plan or experience.selected_tool,
                    verification=experience.verification_status,
                    risk_tier=risk_tier,
                    bayesian_state=bayes_state.to_dict(),
                    precondition_contract=precond.to_dict(),
                )
                logger.info(
                    "strategy created from experience %s for tool %s (tier=%d)",
                    experience.id,
                    experience.selected_tool,
                    risk_tier,
                )

        # 2. Causal Failure Attribution & Scoped Failure Patterns for Failures
        elif not experience.success or critique.should_create_failure_pattern:
            attr_result = FeedbackAttributor.classify(
                user_prompt=experience.user_input,
                tool_args=tool_args,
                tool_error=experience.error,
                verifier_verdict=experience.verification_status,
                signals=[],
            )

            # Only learn a failure pattern if it was an agent execution defect, NOT a user typo/input defect
            if attr_result.strategy_penalizable:
                causal_critique = self._causal_critic.analyze_experience(
                    tool_name=experience.selected_tool,
                    tool_args=tool_args,
                    tool_result=experience.tool_result,
                    error_message=experience.error,
                    verification_status=experience.verification_status,
                )

                # Determine multi-dimensional scope
                if "domain" in tool_args or "url" in tool_args:
                    scope = ScopeLevel.SAME_DOMAIN.value
                    condition = {"domain": tool_args.get("domain") or tool_args.get("url")}
                elif "application" in tool_args:
                    scope = ScopeLevel.SAME_APPLICATION.value
                    condition = {"application": tool_args.get("application")}
                elif causal_critique.primary_failure_type in (
                    CausalFailureType.DEVICE_DISCONNECTED,
                    CausalFailureType.RESOURCE_EXHAUSTED,
                ):
                    scope = ScopeLevel.SAME_DEVICE.value
                    condition = {}
                else:
                    scope = ScopeLevel.EXACT_ARGUMENTS.value
                    condition = {}

                critical = critique.critical_failures
                bad_act = f"{experience.selected_tool}({experience.tool_arguments[:100]})"
                pref_act = (
                    f"avoid: {critical[0].detail}"
                    if critical
                    else f"avoid failure with {experience.selected_tool}"
                )
                if causal_critique.recommended_recovery_action:
                    pref_act = (
                        f"{pref_act}; recovery: {causal_critique.recommended_recovery_action}"
                    )

                self._strategy_store.create_failure_pattern(
                    pattern_name=f"failure:{experience.selected_tool or 'unknown'}",
                    bad_action=bad_act,
                    preferred_action=pref_act,
                    condition=condition,
                    scope=scope,
                    recovery_strategy=causal_critique.recommended_recovery_action or "",
                )
                logger.info(
                    "failure pattern created from experience %s (scope=%s, cause=%s)",
                    experience.id,
                    scope,
                    causal_critique.primary_failure_type.value,
                )

        # Always produce a lesson if we reflected
        if not critique.lesson_summary:
            return None

        lesson = Lesson(
            id=generate_id(),
            experience_id=experience.id,
            created_at=now_ms(),
            summary=critique.lesson_summary,
            generalizable=critique.overall_quality >= 0.7,
            applicable_intents=(
                (experience.interpreted_intent,) if experience.interpreted_intent else ()
            ),
            confidence=critique.overall_quality,
        )
        self._lessons.append(lesson)
        return lesson

    def get_lessons(self) -> list[Lesson]:
        """Return all extracted lessons."""
        return list(self._lessons)

    def load_lessons(self, lessons: list[Lesson]) -> None:
        """Bulk-load lessons from SQLite."""
        self._lessons.extend(lessons)

    @staticmethod
    def _estimate_complexity(exp: Experience) -> float:
        """Estimate task complexity from field lengths (0-1 scale)."""
        score = 0.0
        if exp.user_input:
            score += min(0.2, len(exp.user_input) / 500)
        if exp.plan:
            score += 0.2
        if exp.episode and exp.episode.total_steps > 1:
            score += min(0.3, exp.episode.total_steps * 0.1)
        if exp.tool_arguments:
            score += min(0.15, len(exp.tool_arguments) / 500)
        if exp.context_summary:
            score += 0.15
        return min(1.0, score)

    @staticmethod
    def _safe_parse_json(text: str) -> dict[str, Any]:
        """Parse JSON safely, returning empty dict on failure."""
        if not text:
            return {}
        try:
            import json

            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (ValueError, TypeError):
            pass
        return {}
