"""Strategy Fingerprinting and Conflict Resolution.

Detects contradictory or overlapping strategies targeting the same context.
Enforces deterministic resolution rules:
1. Specificity (more constrained preconditions win)
2. Empirical Bayesian confidence lower bound (CI_lower)
3. Effective sample size (N_eff)
4. Risk tier (lower risk wins)
5. Stable tie-breaker

If ambiguity remains high, declines all conflicting candidates and falls back
to default foundation model reasoning.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


AMBIGUITY_THRESHOLD = 0.05


@dataclass(slots=True, frozen=True)
class StrategyFingerprint:
    """Distinct semantic footprint of what a strategy targets."""

    domain: str
    task_family: str
    target_tool: str
    target_scope: str = "general"

    def digest(self) -> str:
        raw = f"{self.domain}:{self.task_family}:{self.target_tool}:{self.target_scope}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class StrategyCandidate:
    """Wrapper holding a strategy and its empirical performance metrics for resolution."""

    strategy_id: str
    fingerprint: StrategyFingerprint
    ci_lower: float
    effective_n: float
    risk_tier: int  # 1 to 5 (1 is safest)
    precondition_specificity_score: int
    raw_strategy: Any = None


class ConflictResolver:
    """Resolves conflicts among matching strategies."""

    @staticmethod
    def detect_conflicts(candidates: List[StrategyCandidate]) -> Dict[str, List[StrategyCandidate]]:
        """Groups candidates by matching fingerprint digest."""
        groups: Dict[str, List[StrategyCandidate]] = {}
        for c in candidates:
            fp_hash = c.fingerprint.digest()
            if fp_hash not in groups:
                groups[fp_hash] = []
            groups[fp_hash].append(c)
        return {k: v for k, v in groups.items() if len(v) > 1}

    @classmethod
    def resolve_best(
        cls, candidates: List[StrategyCandidate]
    ) -> Tuple[Optional[StrategyCandidate], Optional[str]]:
        """Selects the single best candidate deterministically, or returns (None, reason) if ambiguous."""
        if not candidates:
            return None, "No candidates provided"
        if len(candidates) == 1:
            return candidates[0], None

        # Sort key:
        # 1. Precondition specificity (higher is better)
        # 2. Bayesian CI lower bound (higher is better)
        # 3. Effective sample size (higher is better)
        # 4. Risk tier (lower is better, so negate)
        # 5. Stable strategy ID string (deterministic tie breaker)
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                c.precondition_specificity_score,
                round(c.ci_lower, 3),
                round(c.effective_n, 1),
                -c.risk_tier,
                c.strategy_id,
            ),
            reverse=True,
        )

        top1 = sorted_candidates[0]
        top2 = sorted_candidates[1]

        # Check for ambiguity: if top two have same specificity and closely matched CI bounds,
        # but have conflicting IDs / parameters
        if top1.precondition_specificity_score == top2.precondition_specificity_score:
            diff = abs(top1.ci_lower - top2.ci_lower)
            if diff < AMBIGUITY_THRESHOLD and top1.risk_tier == top2.risk_tier:
                # Ambiguous collision: safe fallback to foundation LLM
                return (
                    None,
                    f"Ambiguous conflict between {top1.strategy_id} and {top2.strategy_id} (CI diff {diff:.3f} < {AMBIGUITY_THRESHOLD})",
                )

        return top1, None
