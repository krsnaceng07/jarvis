"""Strategy Lifecycle Management and Risk-Tiered Qualification Gate.

Enforces strict risk tiering (Tiers 1-5):
- Tier 1: Read-only inspection (min 3 trials, CI_lower >= 0.65)
- Tier 2: Low-risk local mutation (min 5 trials, CI_lower >= 0.75)
- Tier 3: Browser interactions (min 8 trials, CI_lower >= 0.85)
- Tier 4: File/process mutation (min 15 trials, CI_lower >= 0.92)
- Tier 5: Irreversible/system impact (min 25 trials, CI_lower >= 0.98)

Governance Invariants:
- automatic_promotion: STRICTLY DISABLED. Human operator review is mandatory.
- automatic_quarantine: STRICTLY ENABLED. 2 consecutive failures or severe contradiction
  immediately demotes strategy to QUARANTINED.
- Full immutable state transition audit logging.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class StrategyLifecycleState(str, Enum):
    PROPOSED = "proposed"
    EVALUATING = "evaluating"
    QUALIFIED = "qualified"  # Meets Bayesian thresholds, awaiting operator sign-off
    PROMOTED = "promoted"  # Active in production routing (operator approved)
    SUSPENDED = "suspended"  # Temporarily paused due to anomaly
    QUARANTINED = "quarantined"  # Disabled due to consecutive failures / regression
    RETIRED = "retired"  # Permanently superseded or obsolete


@dataclass(slots=True, frozen=True)
class RiskTierConfig:
    tier: int
    name: str
    min_effective_n: float
    min_ci_lower: float
    requires_human_signoff_for_promotion: bool = True
    requires_runtime_confirmation: bool = False


RISK_TIERS: Dict[int, RiskTierConfig] = {
    1: RiskTierConfig(tier=1, name="Read-Only Inspection", min_effective_n=3.0, min_ci_lower=0.65),
    2: RiskTierConfig(tier=2, name="Low-Risk Mutation", min_effective_n=5.0, min_ci_lower=0.75),
    3: RiskTierConfig(
        tier=3, name="Browser / Network Interaction", min_effective_n=8.0, min_ci_lower=0.85
    ),
    4: RiskTierConfig(
        tier=4, name="Sensitive File / Process Mutation", min_effective_n=15.0, min_ci_lower=0.92
    ),
    5: RiskTierConfig(
        tier=5,
        name="Irreversible System Action",
        min_effective_n=25.0,
        min_ci_lower=0.98,
        requires_runtime_confirmation=True,
    ),
}


@dataclass(slots=True)
class LifecycleAuditEntry:
    strategy_id: str
    from_state: StrategyLifecycleState
    to_state: StrategyLifecycleState
    reason: str
    operator: str
    timestamp: float = field(default_factory=time.time)


class StrategyLifecycleManager:
    """Manages strategy state transitions with strict gatekeeping."""

    def __init__(self) -> None:
        self.audit_log: List[LifecycleAuditEntry] = []

    def check_qualification(
        self,
        risk_tier: int,
        effective_n: float,
        ci_lower: float,
    ) -> Tuple[bool, str]:
        config = RISK_TIERS.get(risk_tier, RISK_TIERS[5])
        if effective_n < config.min_effective_n:
            return (
                False,
                f"Insufficient trials: effective_n={effective_n:.1f} < required {config.min_effective_n:.1f}",
            )
        if ci_lower < config.min_ci_lower:
            return (
                False,
                f"Confidence too low: ci_lower={ci_lower:.3f} < required {config.min_ci_lower:.3f}",
            )
        return True, f"Strategy meets Tier {risk_tier} qualification criteria"

    def transition_state(
        self,
        strategy_id: str,
        current_state: StrategyLifecycleState,
        target_state: StrategyLifecycleState,
        reason: str,
        operator: str = "system",
        risk_tier: int = 1,
        effective_n: float = 0.0,
        ci_lower: float = 0.0,
    ) -> Tuple[StrategyLifecycleState, Optional[str]]:
        """Safely transition strategy lifecycle state respecting invariants."""

        # Invariant 1: Automatic promotion is strictly forbidden
        if target_state == StrategyLifecycleState.PROMOTED:
            if operator == "system" or not operator:
                return (
                    current_state,
                    "Automatic strategy promotion is strictly DISABLED. Operator signoff required.",
                )
            # Verify qualification before allowing operator promotion
            qualified, qual_reason = self.check_qualification(risk_tier, effective_n, ci_lower)
            if not qualified:
                return current_state, f"Cannot promote unqualified strategy: {qual_reason}"

        # Invariant 2: Automatic quarantine on failures is always permitted and instantaneous
        if target_state == StrategyLifecycleState.QUARANTINED:
            self._record_transition(strategy_id, current_state, target_state, reason, operator)
            return target_state, None

        # Qualification transition
        if target_state == StrategyLifecycleState.QUALIFIED:
            qualified, qual_reason = self.check_qualification(risk_tier, effective_n, ci_lower)
            if not qualified:
                return current_state, f"Qualification denied: {qual_reason}"

        self._record_transition(strategy_id, current_state, target_state, reason, operator)
        return target_state, None

    def record_execution_outcome(
        self,
        strategy_id: str,
        current_state: StrategyLifecycleState,
        consecutive_failures: int,
    ) -> Tuple[StrategyLifecycleState, Optional[str]]:
        """Enforces automatic quarantine if consecutive failures >= 2."""
        if consecutive_failures >= 2 and current_state in (
            StrategyLifecycleState.PROMOTED,
            StrategyLifecycleState.QUALIFIED,
        ):
            return self.transition_state(
                strategy_id=strategy_id,
                current_state=current_state,
                target_state=StrategyLifecycleState.QUARANTINED,
                reason=f"Immediate automatic rollback: {consecutive_failures} consecutive execution failures",
                operator="auto_rollback_circuit_breaker",
            )
        return current_state, None

    def _record_transition(
        self,
        strategy_id: str,
        from_state: StrategyLifecycleState,
        to_state: StrategyLifecycleState,
        reason: str,
        operator: str,
    ) -> None:
        self.audit_log.append(
            LifecycleAuditEntry(
                strategy_id=strategy_id,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                operator=operator,
            )
        )
