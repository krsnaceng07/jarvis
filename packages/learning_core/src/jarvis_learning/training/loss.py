"""jarvis_learning.training.loss — concrete loss functions and purpose-driven strategies.

Implements Weighted Cross-Entropy, Focal Loss, Direct Preference Optimization (DPO),
Kahneman-Tversky Optimization (KTO), and Graded Margin Ranking Loss.
"""

from __future__ import annotations

import math
from typing import Any


class WeightedCrossEntropyLoss:
    """Standard multi-class cross-entropy with optional sample weights."""

    def __init__(self, eps: float = 1e-7) -> None:
        self.eps = eps

    def compute(self, target_prob: float, sample_weight: float = 1.0) -> float:
        """Compute cross entropy for a single sample."""
        p = max(self.eps, min(1.0 - self.eps, float(target_prob)))
        return -sample_weight * math.log(p)


class WeightedFocalLoss:
    """Focal Loss with sample-level weights from Wave 2 dataset.

    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
    """

    def __init__(self, gamma: float = 2.0, eps: float = 1e-7) -> None:
        self.gamma = gamma
        self.eps = eps

    def compute(self, target_prob: float, sample_weight: float = 1.0) -> float:
        """Compute focal loss for a single target probability in [0, 1]."""
        p = max(self.eps, min(1.0 - self.eps, float(target_prob)))
        focal_weight = (1.0 - p) ** self.gamma
        return -sample_weight * focal_weight * math.log(p)


class GradedMarginLoss:
    """Pairwise margin ranking loss for memory reranking.

    Loss = max(0, margin - (pos_score - neg_score))
    """

    def __init__(self, margin: float = 1.0) -> None:
        self.margin = margin

    def compute(self, pos_score: float, neg_score: float) -> float:
        """Compute margin ranking loss between positive and negative memory candidates."""
        diff = pos_score - neg_score
        return max(0.0, self.margin - diff)


class DPOObjective:
    """Direct Preference Optimization objective for pairwise preference samples."""

    def __init__(self, beta: float = 0.1) -> None:
        self.beta = beta

    def compute(
        self,
        pi_chosen_logp: float,
        pi_rejected_logp: float,
        ref_chosen_logp: float = 0.0,
        ref_rejected_logp: float = 0.0,
    ) -> float:
        """Compute DPO loss: -log(sigmoid(beta * ((pi_c - ref_c) - (pi_r - ref_r))))."""
        chosen_diff = pi_chosen_logp - ref_chosen_logp
        rejected_diff = pi_rejected_logp - ref_rejected_logp
        logits = self.beta * (chosen_diff - rejected_diff)
        # Stable -log(sigmoid(x)) = log(1 + exp(-x))
        if logits > 0:
            return math.log(1.0 + math.exp(-logits))
        return -logits + math.log(1.0 + math.exp(logits))


class KTOObjective:
    """Kahneman-Tversky Optimization objective for unpaired binary desirable/undesirable samples."""

    def __init__(
        self, beta: float = 0.1, desirable_weight: float = 1.0, undesirable_weight: float = 1.0
    ) -> None:
        self.beta = beta
        self.desirable_weight = desirable_weight
        self.undesirable_weight = undesirable_weight

    def compute(
        self,
        pi_logp: float,
        ref_logp: float,
        is_desirable: bool,
        kl_penalty: float = 0.0,
    ) -> float:
        """Compute KTO loss for an individual sample."""
        diff = pi_logp - ref_logp - kl_penalty
        scaled = self.beta * diff
        # Sigmoid value
        sig = 1.0 / (1.0 + math.exp(-min(50.0, max(-50.0, scaled))))

        if is_desirable:
            # 1 - sigmoid(beta * (log_pi - log_ref - KL))
            return self.desirable_weight * (1.0 - sig)
        else:
            # sigmoid(beta * (log_pi - log_ref - KL))
            return self.undesirable_weight * sig


def get_loss_strategy_for_purpose(purpose: str) -> Any:
    """Return the canonical loss strategy for a given training purpose."""
    match purpose.upper():
        case "SFT" | "SUPERVISED_FINE_TUNING":
            return WeightedCrossEntropyLoss()
        case "DPO_PREFERENCE" | "PREFERENCE":
            return DPOObjective()
        case "KTO":
            return KTOObjective()
        case "MEMORY_RANKING" | "RETRIEVAL":
            return GradedMarginLoss()
        case "HARD_TOOL_SELECTION" | "FOCAL":
            return WeightedFocalLoss()
        case _:
            return WeightedCrossEntropyLoss()
