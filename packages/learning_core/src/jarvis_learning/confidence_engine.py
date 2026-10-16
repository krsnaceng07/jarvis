"""Bayesian Beta-Bernoulli Confidence Engine.

Implements rigorous Bayesian belief updating for strategy success rates:
- Prior: Beta(alpha_0=2.0, beta_0=2.0)
- Trust-weighted likelihood updates (TRUSTED=1.0, PARTIALLY_TRUSTED=0.5, UNTRUSTED=0.0)
- Temporal exponential decay with configurable half-life
- Exact numerical Beta credible intervals (root-finding via Lentz continued fractions)
- Explicit separate counters for raw observations, weighted observations,
  independent session counts, and effective sample size.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from jarvis_learning.evidence_model import EvidenceTrustLevel


PRIOR_ALPHA = 2.0
PRIOR_BETA = 2.0
DEFAULT_HALF_LIFE_DAYS = 30.0


class CredibleIntervalError(ArithmeticError):
    """Raised when exact credible interval computation fails or parameters are invalid."""


def _beta_continued_fraction(
    a: float, b: float, x: float, max_iter: int = 200, eps: float = 1e-12
) -> float:
    """Evaluate regularized incomplete beta continued fraction via modified Lentz method."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d

    for m in range(1, max_iter + 1):
        m2 = 2 * m
        # Even step
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c

        # Odd step
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_val = d * c
        h *= del_val

        if abs(del_val - 1.0) < eps:
            return h

    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """Compute regularized incomplete beta function I_x(a, b)."""
    if a <= 0.0 or b <= 0.0:
        raise CredibleIntervalError(f"Beta parameters must be positive: a={a}, b={b}")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    log_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    bt = math.exp(a * math.log(x) + b * math.log(1.0 - x) - log_beta)

    # Use symmetry transform for numerical stability
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _beta_continued_fraction(a, b, x) / a
    else:
        return 1.0 - bt * _beta_continued_fraction(b, a, 1.0 - x) / b


def beta_ppf(p: float, a: float, b: float, max_iter: int = 50, tol: float = 1e-9) -> float:
    """Compute exact Beta distribution quantile (percent point function) via root-finding.

    Finds x in [0, 1] such that I_x(a, b) = p.
    """
    if a <= 0.0 or b <= 0.0:
        raise CredibleIntervalError(f"Invalid Beta shape parameters: a={a}, b={b}")
    if not (0.0 <= p <= 1.0):
        raise CredibleIntervalError(f"Quantile probability p must be in [0, 1]: p={p}")
    if p == 0.0:
        return 0.0
    if p == 1.0:
        return 1.0

    low, high = 0.0, 1.0
    for _ in range(max_iter):
        mid = (low + high) / 2.0
        val = regularized_incomplete_beta(a, b, mid)
        if val < p:
            low = mid
        else:
            high = mid
        if (high - low) < tol:
            return (low + high) / 2.0

    return (low + high) / 2.0


@dataclass(slots=True)
class BayesianConfidenceState:
    """Represents a Bayesian Beta distribution posterior state for a strategy.

    Maintains exact Beta distribution parameters, separate raw and weighted counters,
    and calculates authoritative credible lower bounds via exact quantile root-finding.
    """

    alpha: float = PRIOR_ALPHA
    beta: float = PRIOR_BETA
    raw_successes: int = 0
    raw_failures: int = 0
    weighted_successes: float = 0.0
    weighted_failures: float = 0.0
    independent_sessions_count: int = 0
    effective_n: float = 0.0
    mean: float = 0.5
    ci_lower: float = 0.0
    last_updated_timestamp: float = field(default_factory=time.time)
    computation_status: str = "VALID"

    def __post_init__(self) -> None:
        self._recompute()

    def _recompute(self) -> None:
        total = self.alpha + self.beta
        if total <= 0 or self.alpha <= 0 or self.beta <= 0:
            self.mean = 0.5
            self.ci_lower = 0.0
            self.effective_n = 0.0
            self.computation_status = "CI_COMPUTATION_FAILED"
            return

        self.mean = self.alpha / total
        self.effective_n = max(0.0, total - (PRIOR_ALPHA + PRIOR_BETA))

        try:
            # Authoritative 95% one-sided lower credible bound: Beta 0.05 quantile
            self.ci_lower = max(0.0, min(1.0, beta_ppf(0.05, self.alpha, self.beta)))
            self.computation_status = "VALID"
        except Exception:
            self.ci_lower = 0.0
            self.computation_status = "CI_COMPUTATION_FAILED"

    def update(
        self,
        success: bool,
        trust_level: EvidenceTrustLevel = EvidenceTrustLevel.TRUSTED,
        sample_weight: float = 1.0,
        timestamp: float | None = None,
        is_new_session: bool = False,
    ) -> None:
        """Update posterior belief given an evidence outcome."""
        now = timestamp if timestamp is not None else time.time()

        # Apply temporal decay before new observation
        self.apply_decay(now)

        # Track raw observations
        if success:
            self.raw_successes += 1
        else:
            self.raw_failures += 1

        if is_new_session:
            self.independent_sessions_count += 1

        # Trust factor weighting
        if trust_level == EvidenceTrustLevel.TRUSTED:
            trust_weight = 1.0
        elif trust_level == EvidenceTrustLevel.PARTIALLY_TRUSTED:
            trust_weight = 0.5
        else:
            trust_weight = 0.0

        effective_delta = max(0.0, sample_weight * trust_weight)
        if effective_delta > 0.0:
            if success:
                self.alpha += effective_delta
                self.weighted_successes += effective_delta
            else:
                self.beta += effective_delta
                self.weighted_failures += effective_delta

        self.last_updated_timestamp = now
        self._recompute()

    def apply_decay(
        self, current_time: float, half_life_days: float = DEFAULT_HALF_LIFE_DAYS
    ) -> None:
        """Apply exponential decay toward the prior based on elapsed time."""
        if current_time <= self.last_updated_timestamp or half_life_days <= 0:
            return

        elapsed_seconds = current_time - self.last_updated_timestamp
        elapsed_days = elapsed_seconds / 86400.0
        decay_factor = math.exp(-math.log(2.0) * (elapsed_days / half_life_days))

        excess_alpha = max(0.0, self.alpha - PRIOR_ALPHA)
        excess_beta = max(0.0, self.beta - PRIOR_BETA)

        self.alpha = PRIOR_ALPHA + (excess_alpha * decay_factor)
        self.beta = PRIOR_BETA + (excess_beta * decay_factor)
        self.last_updated_timestamp = current_time
        self._recompute()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": round(self.alpha, 4),
            "beta": round(self.beta, 4),
            "raw_successes": self.raw_successes,
            "raw_failures": self.raw_failures,
            "weighted_successes": round(self.weighted_successes, 4),
            "weighted_failures": round(self.weighted_failures, 4),
            "independent_sessions_count": self.independent_sessions_count,
            "effective_n": round(self.effective_n, 4),
            "mean": round(self.mean, 4),
            "ci_lower": round(self.ci_lower, 4),
            "last_updated_timestamp": self.last_updated_timestamp,
            "computation_status": self.computation_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BayesianConfidenceState:
        return cls(
            alpha=float(data.get("alpha", PRIOR_ALPHA)),
            beta=float(data.get("beta", PRIOR_BETA)),
            raw_successes=int(data.get("raw_successes", 0)),
            raw_failures=int(data.get("raw_failures", 0)),
            weighted_successes=float(data.get("weighted_successes", 0.0)),
            weighted_failures=float(data.get("weighted_failures", 0.0)),
            independent_sessions_count=int(data.get("independent_sessions_count", 0)),
            effective_n=float(data.get("effective_n", 0.0)),
            mean=float(data.get("mean", 0.5)),
            ci_lower=float(data.get("ci_lower", 0.0)),
            last_updated_timestamp=float(data.get("last_updated_timestamp", time.time())),
            computation_status=str(data.get("computation_status", "VALID")),
        )
