"""jarvis_learning.datasets.negative_mining — hard negative generation.

Generates contextually valid negative samples for policy training.
Without negatives, a tool-selection model only learns what to do,
never what NOT to do.

Sources for hard negatives:
1. Previously failed tool calls for the same intent
2. Anti-pattern benchmark cases
3. Tool selected before user correction
4. Duplicate-action patterns (e.g. opening a new tab when one exists)
5. Wrong-tool-type mistakes (browser when filesystem needed)

NOT used: random unrelated tools (too easy, doesn't teach discrimination).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..experience import Experience, generate_id
from ..strategies import FailurePattern, StrategyStore
from .schema import DatasetSample, DatasetTarget, LabelQuality, DEFAULT_SAMPLE_WEIGHTS
from .lineage import SampleLineage


@dataclass(frozen=True, slots=True)
class NegativeSample:
    """A contextually valid negative training sample."""

    input_data: dict[str, Any]
    negative_tool: str
    negative_reason: str
    source: str  # "failure_pattern" | "correction" | "failed_attempt"
    confidence: float


class HardNegativeMiner:
    """Generates hard negative samples from real failure data.

    Every positive sample can produce 0..N negatives depending on
    available failure data.  Quality over quantity — each negative
    must be a contextually plausible wrong answer.
    """

    def __init__(self, strategy_store: StrategyStore) -> None:
        self._store = strategy_store

    def mine_tool_negatives(
        self,
        positive_exp: Experience,
        all_tools: list[str] | None = None,
    ) -> list[NegativeSample]:
        """Generate hard negatives for a positive tool-policy sample.

        Uses real failure data, not random tool sampling.
        """
        negatives: list[NegativeSample] = []

        if not positive_exp.selected_tool:
            return negatives

        # Source 1: Failure patterns for this tool/intent
        patterns = self._store.all_failure_patterns()
        for pattern in patterns:
            # The bad_action is a negative for any intent that matches
            if self._is_relevant_pattern(positive_exp, pattern):
                negatives.append(
                    NegativeSample(
                        input_data={
                            "user_input": positive_exp.user_input,
                            "context": positive_exp.context_summary or "",
                        },
                        negative_tool=self._extract_tool_from_action(pattern.bad_action),
                        negative_reason=f"known failure pattern: {pattern.pattern_name}",
                        source="failure_pattern",
                        confidence=pattern.confidence,
                    )
                )

        # Source 2: From user corrections — the tool used BEFORE
        # correction is a hard negative
        if positive_exp.user_feedback in ("correction", "user_correction"):
            # The current tool was the corrected-to tool.
            # Any previously tried tool for similar intent is a negative.
            negatives.extend(self._negatives_from_corrections(positive_exp))

        # Source 3: Wrong-type negatives (e.g., browser vs filesystem)
        type_negatives = self._wrong_type_negatives(positive_exp, all_tools or [])
        negatives.extend(type_negatives)

        # Deduplicate by negative_tool
        seen: set[str] = set()
        unique: list[NegativeSample] = []
        for neg in negatives:
            if neg.negative_tool and neg.negative_tool not in seen:
                seen.add(neg.negative_tool)
                unique.append(neg)

        return unique

    def negatives_to_samples(
        self,
        negatives: list[NegativeSample],
        source_experience_id: str,
        target: str = DatasetTarget.TOOL_POLICY,
    ) -> list[DatasetSample]:
        """Convert NegativeSamples to DatasetSamples."""
        samples: list[DatasetSample] = []
        for neg in negatives:
            lineage = SampleLineage.from_experience(
                sample_id=generate_id(),
                experience_id=source_experience_id,
                created_by="negative_miner",
            )
            samples.append(
                DatasetSample(
                    sample_id=lineage.sample_id,
                    target=target,
                    input_data=neg.input_data,
                    label={
                        "tool": neg.negative_tool,
                        "is_negative": True,
                        "negative_reason": neg.negative_reason,
                    },
                    label_quality=LabelQuality.WRONG,
                    label_confidence=neg.confidence,
                    label_source=neg.source,
                    sample_weight=DEFAULT_SAMPLE_WEIGHTS[LabelQuality.WRONG],
                    provenance={},
                    lineage=lineage.to_dict(),
                    quality_score=neg.confidence,
                    source_experience_id=source_experience_id,
                )
            )
        return samples

    def _is_relevant_pattern(self, exp: Experience, pattern: FailurePattern) -> bool:
        """Check if a failure pattern is relevant to this experience."""
        # The pattern's bad_action should involve a different tool
        bad_tool = self._extract_tool_from_action(pattern.bad_action)
        if bad_tool == exp.selected_tool:
            return False
        if not bad_tool:
            return False
        # Check intent overlap — pattern name should relate to the task
        intent = (exp.interpreted_intent or exp.user_input).lower()
        pattern_text = (pattern.pattern_name + " " + pattern.bad_action).lower()
        # Simple keyword overlap check
        intent_words = set(intent.split())
        pattern_words = set(pattern_text.split())
        overlap = len(intent_words & pattern_words)
        return overlap >= 1

    def _negatives_from_corrections(self, exp: Experience) -> list[NegativeSample]:
        """Generate negatives from the correction context.

        When a user corrected JARVIS, the behavior before correction
        is a hard negative.
        """
        # Look for strategies where the tool differs from the corrected one
        strategies = self._store.find_strategies_for_intent(
            exp.interpreted_intent or exp.user_input[:100]
        )
        negatives: list[NegativeSample] = []
        for strategy in strategies:
            if (
                strategy.tool != exp.selected_tool
                and strategy.success_count < strategy.attempt_count
            ):
                negatives.append(
                    NegativeSample(
                        input_data={
                            "user_input": exp.user_input,
                            "context": exp.context_summary or "",
                        },
                        negative_tool=strategy.tool,
                        negative_reason=(
                            f"previously tried and corrected by user "
                            f"(success rate: {strategy.success_rate:.0%})"
                        ),
                        source="correction",
                        confidence=0.8,
                    )
                )
        return negatives

    @staticmethod
    def _wrong_type_negatives(
        exp: Experience,
        all_tools: list[str],
    ) -> list[NegativeSample]:
        """Generate negatives from wrong tool categories.

        If the correct tool is browser.navigate_tab, then filesystem.open
        is a wrong-type negative.
        """
        if not exp.selected_tool or not all_tools:
            return []

        correct_category = exp.selected_tool.split(".")[0]
        negatives: list[NegativeSample] = []

        for tool in all_tools:
            tool_category = tool.split(".")[0]
            if tool_category != correct_category and tool != exp.selected_tool:
                negatives.append(
                    NegativeSample(
                        input_data={
                            "user_input": exp.user_input,
                            "context": exp.context_summary or "",
                        },
                        negative_tool=tool,
                        negative_reason=(
                            f"wrong tool type: {tool_category} when {correct_category} needed"
                        ),
                        source="wrong_type",
                        confidence=0.6,
                    )
                )

        # Limit wrong-type negatives to avoid flooding
        return negatives[:3]

    @staticmethod
    def _extract_tool_from_action(action: str) -> str:
        """Extract a tool name from a free-text action description."""
        # Look for patterns like "browser.new_tab" in the action text
        import re

        match = re.search(r"(\w+\.\w+)", action)
        return match.group(1) if match else ""
