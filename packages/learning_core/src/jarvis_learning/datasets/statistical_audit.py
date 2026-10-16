"""jarvis_learning.datasets.statistical_audit — distribution and balance analytics.

Computes:
- Label distribution and positive/negative ratios
- Source/session concentration (Gini coefficient, top-1 dominance)
- Tool category balance
- Risk tier distributions
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class DistributionAuditReport:
    total_samples: int
    label_distribution: dict[str, int]
    negative_sample_ratio: float
    session_top1_ratio: float
    tool_top1_ratio: float
    is_balanced: bool
    warnings: tuple[str, ...]


def _gini_coefficient(counts: Sequence[int]) -> float:
    """Calculate Gini coefficient for inequality in counts (0 = perfect equality, 1 = total concentration)."""
    if not counts or sum(counts) == 0:
        return 0.0
    sorted_counts = sorted(counts)
    n = len(sorted_counts)
    total = sum(sorted_counts)
    cumulative = 0
    gini_sum = 0.0
    for idx, c in enumerate(sorted_counts):
        cumulative += c
        gini_sum += (idx + 1) * c
    return max(0.0, min(1.0, (2 * gini_sum) / (n * total) - (n + 1) / n))


class StatisticalAuditor:
    """Audits dataset samples for distribution balance and excessive concentration."""

    def audit(self, samples: Sequence[Any]) -> DistributionAuditReport:
        if not samples:
            return DistributionAuditReport(
                total_samples=0,
                label_distribution={},
                negative_sample_ratio=0.0,
                session_top1_ratio=0.0,
                tool_top1_ratio=0.0,
                is_balanced=True,
                warnings=(),
            )

        total = len(samples)
        label_counts = Counter(getattr(s, "label_quality", "unknown") for s in samples)
        negative_count = sum(
            1 for s in samples if getattr(s, "label", {}).get("is_negative", False)
        )
        neg_ratio = negative_count / total if total > 0 else 0.0

        session_counts = Counter(
            getattr(s, "lineage", {}).get("source_session_id", "") for s in samples
        )
        # Exclude empty session strings from top1 ratio
        valid_sess = [c for s_id, c in session_counts.items() if s_id]
        top_sess_ratio = max(valid_sess) / total if valid_sess else 0.0

        tool_counts = Counter(getattr(s, "label", {}).get("tool", "") for s in samples)
        valid_tools = [c for t, c in tool_counts.items() if t]
        top_tool_ratio = max(valid_tools) / total if valid_tools else 0.0

        warnings: list[str] = []
        if total >= 20 and neg_ratio == 0.0:
            warnings.append("Dataset contains 0% negative contrast samples")
        if total >= 20 and top_sess_ratio > 0.60:
            warnings.append(
                f"High session concentration: single session accounts for {top_sess_ratio:.1%}"
            )
        if total >= 20 and top_tool_ratio > 0.70:
            warnings.append(
                f"High tool concentration: single tool accounts for {top_tool_ratio:.1%}"
            )

        is_balanced = len(warnings) == 0

        return DistributionAuditReport(
            total_samples=total,
            label_distribution=dict(label_counts),
            negative_sample_ratio=round(neg_ratio, 4),
            session_top1_ratio=round(top_sess_ratio, 4),
            tool_top1_ratio=round(top_tool_ratio, 4),
            is_balanced=is_balanced,
            warnings=tuple(warnings),
        )
