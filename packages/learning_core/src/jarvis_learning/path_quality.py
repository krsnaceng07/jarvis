from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SuccessQuality:
    goal_satisfied: bool
    target_correct: bool
    duplicate_free: bool
    side_effect_clean: bool
    policy_clean: bool
    intent_alignment_score: float = 1.0

    @property
    def is_worthy(self) -> bool:
        return (
            self.goal_satisfied
            and self.target_correct
            and self.duplicate_free
            and self.side_effect_clean
            and self.policy_clean
            and self.intent_alignment_score >= 0.8
        )


@dataclass(frozen=True, slots=True)
class PathEvaluation:
    action_count: int
    unnecessary_action_count: int
    duplicate_action_count: int
    resource_reuse_score: float
    latency_ms: int
    recovery_count: int
    canonical_path_match: bool
    efficiency_score: float

    @property
    def is_efficient(self) -> bool:
        return self.efficiency_score >= 0.75 and self.duplicate_action_count == 0


class PathQualityEvaluator:
    @classmethod
    def evaluate(
        cls,
        user_input: str = "",
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: Any = None,
        physical_verified: bool = True,
        context: dict[str, Any] | None = None,
        is_duplicate: bool = False,
        unnecessary_steps: int = 0,
        user_feedback: str = "",
        # Direct keyword override support:
        goal_satisfied: bool | None = None,
        correct_target: bool | None = None,
        duplicate_free: bool | None = None,
        side_effects_clean: bool | None = None,
        policy_compliant: bool | None = None,
        actual_steps: int | None = None,
        optimal_steps: int | None = None,
        duplicate_attempts: int = 0,
        execution_time_ms: float = 0.0,
    ) -> tuple[SuccessQuality, PathEvaluation, bool]:
        if goal_satisfied is not None:
            g_sat = bool(goal_satisfied)
            t_corr = correct_target if correct_target is not None else True
            d_free = duplicate_free if duplicate_free is not None else True
            s_clean = side_effects_clean if side_effects_clean is not None else True
            p_clean = policy_compliant if policy_compliant is not None else True
            act_steps = actual_steps if actual_steps is not None else 1
            opt_steps = optimal_steps if optimal_steps is not None else 1
            dup_att = duplicate_attempts

            sq = SuccessQuality(
                goal_satisfied=g_sat,
                target_correct=t_corr,
                duplicate_free=d_free,
                side_effect_clean=s_clean,
                policy_clean=p_clean,
                intent_alignment_score=1.0,
            )
            step_penalty = max(0.0, (act_steps - opt_steps) * 0.1)
            dup_penalty = dup_att * 0.25
            eff = max(0.0, 1.0 - (step_penalty + dup_penalty))
            pe = PathEvaluation(
                action_count=act_steps,
                unnecessary_action_count=max(0, act_steps - opt_steps),
                duplicate_action_count=dup_att,
                resource_reuse_score=1.0,
                latency_ms=int(execution_time_ms),
                recovery_count=0,
                canonical_path_match=t_corr and d_free,
                efficiency_score=eff,
            )
            worthy = g_sat and sq.is_worthy and pe.is_efficient
            return sq, pe, worthy

        ctx = context or {}
        tool_args = tool_args or {}

        # Check target correctness (e.g. if an existing target tab or window existed, was it used?)
        existing_target = ctx.get("existing_target_id")
        target_correct = True
        if existing_target:
            used_target = (
                tool_args.get("tab_id") or tool_args.get("window_id") or tool_args.get("pid")
            )
            if used_target and str(used_target) != str(existing_target):
                target_correct = False
            elif tool_name in ("browser.new_tab", "browser.open_window"):
                # Spawned new tab instead of reusing existing
                target_correct = False

        # Intent alignment from feedback
        intent_alignment = 1.0
        if user_feedback in ("correction", "user_correction", "incorrect"):
            intent_alignment = 0.0
        elif user_feedback in ("thumbs_down", "negative"):
            intent_alignment = 0.3

        # Check for duplicate action
        dup_count = 1 if is_duplicate else 0

        # Check side effects
        side_effect_clean = True
        if isinstance(tool_result, dict) and tool_result.get("unintended_side_effects"):
            side_effect_clean = False

        success_quality = SuccessQuality(
            goal_satisfied=physical_verified,
            target_correct=target_correct,
            duplicate_free=not is_duplicate,
            side_effect_clean=side_effect_clean,
            policy_clean=True,
            intent_alignment_score=intent_alignment,
        )

        resource_reuse = (
            1.0 if (existing_target and target_correct) or (not existing_target) else 0.0
        )
        eff_penalty = (
            (dup_count * 0.4) + (unnecessary_steps * 0.2) + (0.3 if not target_correct else 0.0)
        )
        efficiency = max(0.0, 1.0 - eff_penalty)

        path_eval = PathEvaluation(
            action_count=1 + unnecessary_steps,
            unnecessary_action_count=unnecessary_steps,
            duplicate_action_count=dup_count,
            resource_reuse_score=resource_reuse,
            latency_ms=ctx.get("duration_ms", 100),
            recovery_count=0,
            canonical_path_match=target_correct and not is_duplicate,
            efficiency_score=efficiency,
        )

        strategy_worthy = physical_verified and success_quality.is_worthy and path_eval.is_efficient

        return success_quality, path_eval, strategy_worthy
