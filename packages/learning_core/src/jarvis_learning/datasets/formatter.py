"""jarvis_learning.datasets.formatter — target-specific format converters.

Each formatter converts Wave 1 types (Experience, Strategy) into
``DatasetSample`` instances through the common schema contract.

Tool Policy: positive + negative samples with label quality
Memory Reranker: graded relevance 0-3
Strategy Predictor: candidate/rejected tracking
"""

from __future__ import annotations

from typing import Any

from ..experience import Experience, generate_id
from ..strategies import Strategy
from .label_quality import LabelAssessment
from .lineage import SampleLineage
from .schema import (
    DEFAULT_SAMPLE_WEIGHTS,
    DatasetSample,
    DatasetTarget,
    LabelQuality,
)


class ToolPolicyFormatter:
    """Format for Model A: Tool Selection Policy.

    Outputs positive samples (correct tool) and integrates with
    HardNegativeMiner for negative samples.
    """

    def format(
        self,
        exp: Experience,
        label_assessment: LabelAssessment,
        provenance_dict: dict[str, Any],
    ) -> DatasetSample | None:
        """Create a positive tool-policy sample.

        Returns None if the experience lacks required data.
        Negative samples are created separately by HardNegativeMiner.
        """
        if not exp.selected_tool:
            return None
        if label_assessment.quality == LabelQuality.UNKNOWN:
            return None

        sample_id = generate_id()
        lineage = SampleLineage.from_experience(
            sample_id=sample_id,
            experience_id=exp.id,
            session_id=exp.session_id,
            agent_id=exp.agent_id,
            episode_id=(exp.episode.episode_id if exp.episode else ""),
            created_by="tool_policy_formatter",
            approval_reason=label_assessment.reason,
        )

        weight = DEFAULT_SAMPLE_WEIGHTS.get(label_assessment.quality, 0.0)

        return DatasetSample(
            sample_id=sample_id,
            target=DatasetTarget.TOOL_POLICY,
            input_data={
                "user_input": exp.user_input,
                "interpreted_intent": exp.interpreted_intent or "",
                "context": exp.context_summary or "",
                "plan": exp.plan or "",
            },
            label={
                "tool": exp.selected_tool,
                "args_pattern": exp.tool_arguments[:200] if exp.tool_arguments else "",
                "is_negative": False,
                "alternative_actions": list(label_assessment.alternative_actions),
            },
            label_quality=label_assessment.quality,
            label_confidence=label_assessment.confidence,
            label_source="tool_result_verification",
            sample_weight=weight,
            provenance=provenance_dict,
            lineage=lineage.to_dict(),
            quality_score=exp.confidence,
            source_experience_id=exp.id,
        )


class MemoryRerankerFormatter:
    """Format for Model B: Memory Reranker with graded relevance.

    Grades:
    0 = irrelevant — memory retrieved but task failed
    1 = weakly related — memory retrieved, task succeeded, no proof of use
    2 = useful context — (requires explicit tracking, Wave 3)
    3 = directly necessary — memory retrieved, used, task verified success

    For Wave 2, grades 0 and 3 are derivable.  Grades 1-2 are set
    to ``unknown`` and excluded from training.
    """

    def format(self, exp: Experience) -> DatasetSample | None:
        """Create a memory-reranker sample if memory context exists."""
        if not exp.context_summary:
            return None

        # Determine grade
        if exp.success and exp.verification_status == "verified_success":
            grade = 3
            quality = LabelQuality.OPTIMAL
            confidence = 0.7
        elif not exp.success:
            grade = 0
            quality = LabelQuality.WRONG
            confidence = 0.6
        else:
            # Unverified success — we don't know if memory helped
            grade = 1
            quality = LabelQuality.UNKNOWN
            confidence = 0.3

        # Skip unknown grades from training
        if quality == LabelQuality.UNKNOWN:
            return None

        sample_id = generate_id()
        lineage = SampleLineage.from_experience(
            sample_id=sample_id,
            experience_id=exp.id,
            session_id=exp.session_id,
            created_by="memory_reranker_formatter",
        )

        return DatasetSample(
            sample_id=sample_id,
            target=DatasetTarget.MEMORY_RERANKER,
            input_data={
                "query": exp.user_input,
                "memory": exp.context_summary,
            },
            label={
                "relevance": grade,
                "retrieved": True,
                "injected": bool(exp.context_summary),
                "used_by_model": grade == 3,
                "usefulness_confidence": confidence,
            },
            label_quality=quality,
            label_confidence=confidence,
            label_source="outcome_correlation",
            sample_weight=DEFAULT_SAMPLE_WEIGHTS.get(quality, 0.0),
            provenance={},
            lineage=lineage.to_dict(),
            quality_score=confidence,
            source_experience_id=exp.id,
        )


class StrategyPredictorFormatter:
    """Format for Model C: Strategy Success Predictor.

    Records candidate strategies, selected strategy, and outcome.
    Untested strategies are NOT marked as failures.
    """

    def format(
        self,
        exp: Experience,
        candidate_strategies: list[Strategy],
        selected_strategy: Strategy | None,
    ) -> list[DatasetSample]:
        """Create strategy prediction samples.

        One sample per candidate strategy, with the selected one
        marked and its outcome recorded.  Unselected strategies
        get label_quality=UNKNOWN (excluded from training by default).
        """
        if not candidate_strategies:
            return []

        samples: list[DatasetSample] = []
        for strategy in candidate_strategies:
            is_selected = selected_strategy is not None and strategy.id == selected_strategy.id

            if is_selected:
                quality = LabelQuality.OPTIMAL if exp.success else LabelQuality.WRONG
                confidence = 0.8 if exp.success else 0.7
            else:
                # Untested — do NOT mark as failure
                quality = LabelQuality.UNKNOWN
                confidence = 0.2

            sample_id = generate_id()
            lineage = SampleLineage.from_experience(
                sample_id=sample_id,
                experience_id=exp.id,
                session_id=exp.session_id,
                created_by="strategy_predictor_formatter",
            )

            samples.append(
                DatasetSample(
                    sample_id=sample_id,
                    target=DatasetTarget.STRATEGY_PREDICTOR,
                    input_data={
                        "task": exp.user_input,
                        "strategy_id": strategy.id,
                        "strategy_intent": strategy.intent,
                        "strategy_tool": strategy.tool,
                        "candidates_count": len(candidate_strategies),
                    },
                    label={
                        "selected": is_selected,
                        "outcome": "success" if exp.success else "failure",
                        "selection_reason": (
                            "highest_confidence" if is_selected else "not_selected"
                        ),
                        "succeeded": exp.success if is_selected else None,
                    },
                    label_quality=quality,
                    label_confidence=confidence,
                    label_source="strategy_outcome",
                    sample_weight=DEFAULT_SAMPLE_WEIGHTS.get(quality, 0.0),
                    provenance={},
                    lineage=lineage.to_dict(),
                    quality_score=confidence,
                    source_experience_id=exp.id,
                )
            )

        return samples
