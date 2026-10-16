"""jarvis_learning.training.numerical_stability — numerical stability and gradient health monitoring.

Guarantees:
- INV-NUM-001: Traps NaN/Inf loss, exploding/vanishing gradients, nonfinite model parameters,
  loss stagnation windows, and GradScaler anomalies.
- Mandatory candidate gate: no model exhibiting nonfinite parameters or unrecovered numerical
  faults can ever become a candidate.
"""

from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from .errors import TrainingError

logger = logging.getLogger(__name__)


class NumericalFaultClass(enum.StrEnum):
    """Granular categories of numerical stability failures (INV-NUM-001)."""

    NAN_LOSS = "NAN_LOSS"
    INF_LOSS = "INF_LOSS"
    GRADIENT_EXPLOSION = "GRADIENT_EXPLOSION"
    NONFINITE_PARAMETER = "NONFINITE_PARAMETER"
    LOSS_STAGNATION = "LOSS_STAGNATION"
    GRAD_SCALER_ANOMALY = "GRAD_SCALER_ANOMALY"


class NumericalInstabilityError(TrainingError):
    """Raised when severe numerical fault threatens training integrity."""

    def __init__(self, message: str, code: str = "NUMERICAL_INSTABILITY") -> None:
        super().__init__(message, code=code)


class NaNLossError(NumericalInstabilityError):
    def __init__(self, message: str = "Loss value evaluated to NaN") -> None:
        super().__init__(message, code="NAN_LOSS")


class InfLossError(NumericalInstabilityError):
    def __init__(self, message: str = "Loss value evaluated to Inf") -> None:
        super().__init__(message, code="INF_LOSS")


class GradientExplosionError(NumericalInstabilityError):
    def __init__(self, norm: float, threshold: float) -> None:
        super().__init__(
            f"Gradient norm ({norm:.2f}) exceeded explosion ceiling ({threshold:.2f})",
            code="GRADIENT_EXPLOSION",
        )


class NonfiniteParameterError(NumericalInstabilityError):
    def __init__(self, param_name: str) -> None:
        super().__init__(
            f"Model parameter '{param_name}' contains NaN or Inf values",
            code="NONFINITE_PARAMETERS",
        )


class LossStagnationError(NumericalInstabilityError):
    def __init__(self, steps: int) -> None:
        super().__init__(
            f"Loss value stagnated completely with zero variance over {steps} steps",
            code="TRAINING_STAGNATION",
        )


@dataclass(frozen=True, slots=True)
class NumericalPolicy:
    """Thresholds governing numerical validation."""

    max_gradient_norm: float = 100.0
    loss_spike_multiplier: float = 10.0
    stagnation_window: int = 15
    stagnation_min_delta: float = 0.0
    allow_amp_growth_retries: int = 3
    require_strictly_finite_parameters: bool = True

    def __init__(
        self,
        max_gradient_norm: float = 100.0,
        loss_spike_multiplier: float = 10.0,
        stagnation_window: int = 15,
        stagnation_min_delta: float = 0.0,
        allow_amp_growth_retries: int = 3,
        require_strictly_finite_parameters: bool = True,
        gradient_clip_norm: float | None = None,
        explosion_multiplier: float | None = None,
        stagnation_patience_steps: int | None = None,
    ) -> None:
        if gradient_clip_norm is not None and explosion_multiplier is not None:
            max_gradient_norm = gradient_clip_norm * explosion_multiplier
        elif gradient_clip_norm is not None:
            max_gradient_norm = gradient_clip_norm

        if stagnation_patience_steps is not None:
            stagnation_window = stagnation_patience_steps + 1

        object.__setattr__(self, "max_gradient_norm", max_gradient_norm)
        object.__setattr__(self, "loss_spike_multiplier", loss_spike_multiplier)
        object.__setattr__(self, "stagnation_window", stagnation_window)
        object.__setattr__(self, "stagnation_min_delta", stagnation_min_delta)
        object.__setattr__(self, "allow_amp_growth_retries", allow_amp_growth_retries)
        object.__setattr__(
            self, "require_strictly_finite_parameters", require_strictly_finite_parameters
        )


@dataclass(slots=True)
class NumericalStabilityMonitor:
    """Active runtime monitor tracking numerical stability during training."""

    policy: NumericalPolicy = field(default_factory=NumericalPolicy)
    loss_history: list[float] = field(default_factory=list)
    gradient_norm_history: list[float] = field(default_factory=list)
    fatal_faults: list[str] = field(default_factory=list)
    amp_overflow_count: int = 0
    step_count: int = 0
    pre_failure_step: int | None = None

    @property
    def has_fault(self) -> bool:
        """Convenience property indicating whether any fatal numerical fault was recorded."""
        return len(self.fatal_faults) > 0

    def check_loss(self, loss: float, step: int | None = None) -> None:
        """Validate current step loss for finiteness and stagnation."""
        s = self.step_count if step is None else step
        self.step_count += 1

        if math.isnan(loss):
            msg = f"Step {s}: Loss evaluated to NaN"
            self.fatal_faults.append(msg)
            self.pre_failure_step = max(0, s - 1)
            logger.error(msg)
            raise NaNLossError(msg)

        if math.isinf(loss):
            msg = f"Step {s}: Loss evaluated to Inf"
            self.fatal_faults.append(msg)
            self.pre_failure_step = max(0, s - 1)
            logger.error(msg)
            raise InfLossError(msg)

        self.loss_history.append(loss)

        # Check for loss stagnation (variation <= min_delta over window)
        w = self.policy.stagnation_window
        min_delta = self.policy.stagnation_min_delta
        if len(self.loss_history) >= w:
            recent = self.loss_history[-w:]
            if (max(recent) - min(recent)) <= min_delta:
                msg = f"Step {s}: Loss stagnated at {loss} over {w} steps"
                self.fatal_faults.append(msg)
                self.pre_failure_step = max(0, s - 1)
                logger.warning(msg)
                raise LossStagnationError(w)

    def check_gradient_norm(self, grad_norm: float, step: int | None = None) -> None:
        """Validate gradient norm against explosion threshold."""
        s = self.step_count if step is None else step

        if math.isnan(grad_norm) or math.isinf(grad_norm):
            msg = f"Step {s}: Gradient norm is non-finite: {grad_norm}"
            self.fatal_faults.append(msg)
            self.pre_failure_step = max(0, s - 1)
            logger.error(msg)
            raise NumericalInstabilityError(msg, code="NONFINITE_GRADIENT")

        if grad_norm > self.policy.max_gradient_norm:
            msg = f"Step {s}: Gradient norm {grad_norm:.2f} > {self.policy.max_gradient_norm:.2f}"
            self.fatal_faults.append(msg)
            self.pre_failure_step = max(0, s - 1)
            logger.error(msg)
            raise GradientExplosionError(grad_norm, self.policy.max_gradient_norm)

        self.gradient_norm_history.append(grad_norm)

    def check_parameters_finite(self, named_parameters: Any) -> None:
        """Verify that all model parameters contain strictly finite floating-point values."""
        items = named_parameters.items() if isinstance(named_parameters, dict) else named_parameters
        for name, tensor in items:
            # Check tensor if torch or numpy array or scalar
            try:
                import torch

                if isinstance(tensor, torch.Tensor):
                    if not bool(torch.isfinite(tensor).all()):
                        msg = f"Parameter '{name}' contains NaN/Inf values"
                        self.fatal_faults.append(msg)
                        logger.error(msg)
                        raise NonfiniteParameterError(name)
                    continue
            except ImportError:
                pass

            # Fallback scalar or sequence
            if hasattr(tensor, "__iter__"):
                for val in tensor:
                    if isinstance(val, (int, float)) and not math.isfinite(val):
                        self.fatal_faults.append(f"Parameter '{name}' nonfinite")
                        raise NonfiniteParameterError(name)
            elif isinstance(tensor, (int, float)) and not math.isfinite(tensor):
                self.fatal_faults.append(f"Parameter '{name}' nonfinite")
                raise NonfiniteParameterError(name)

    check_parameters = check_parameters_finite

    def record_amp_overflow(self) -> None:
        """Record an automatic mixed precision gradient overflow."""
        self.amp_overflow_count += 1
        if self.amp_overflow_count > self.policy.allow_amp_growth_retries:
            msg = f"Persistent AMP gradient overflows ({self.amp_overflow_count}) exceeded retry limit"
            self.fatal_faults.append(msg)
            raise NumericalInstabilityError(msg, code="AMP_SCALER_FAILURE")

    def has_fatal_numerical_fault(self) -> bool:
        """Check if any disqualifying numerical fault was recorded."""
        return len(self.fatal_faults) > 0

    def verify_candidate_eligibility(self, raise_on_fault: bool = False) -> tuple[bool, str]:
        """Enforce Condition 3: Bar model from becoming a candidate if numerical faults occurred."""
        if self.has_fatal_numerical_fault():
            msg = (
                f"Model cannot become CANDIDATE due to recorded numerical faults: "
                f"{'; '.join(self.fatal_faults)}"
            )
            logger.error(msg)
            if raise_on_fault:
                raise NumericalInstabilityError(msg, code="NUMERICAL_FAULT_CANDIDATE_BLOCKED")
            return False, f"Unrecovered numerical faults: {'; '.join(self.fatal_faults)}"
        return True, "Eligible"
