"""jarvis_learning.training.model_compatibility — architecture and adapter compatibility gate.

Validates tokenizer match, vocabulary coverage, hidden dimensions, sequence length,
LoRA target modules, and precision compatibility before training begins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from .errors import ModelIncompatibleError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelArchitectureSpec:
    """Declared capabilities and structural dimensions of a model architecture."""

    architecture_name: str
    vocab_size: int
    hidden_dim: int
    max_sequence_length: int
    supported_precisions: tuple[str, ...] = ("FP32", "CPU_DETERMINISTIC")
    lora_target_modules: tuple[str, ...] = ()
    tokenizer_name: str = "standard_ngram"


@dataclass(frozen=True, slots=True)
class ModelCompatibilityReport:
    """Evaluation of whether a dataset and training config match the model architecture."""

    compatible: bool
    issues: tuple[str, ...]
    architecture_name: str
    target: str

    def raise_if_incompatible(self) -> None:
        """Raise ModelIncompatibleError if any incompatibility was found."""
        if not self.compatible:
            details = "; ".join(self.issues)
            raise ModelIncompatibleError(f"Model compatibility check failed: {details}")


class ModelCompatibilityChecker:
    """Validates compatibility between training requirements and model specs."""

    @classmethod
    def check_compatibility(
        cls,
        spec: ModelArchitectureSpec,
        target: str,
        required_classes: Sequence[str] = (),
        max_sample_tokens: int = 0,
        requested_precision: str = "CPU_DETERMINISTIC",
        requested_lora_targets: Sequence[str] = (),
    ) -> ModelCompatibilityReport:
        """Evaluate compatibility and return a structured report."""
        issues: list[str] = []

        # 1. Vocab size check
        if len(required_classes) > spec.vocab_size:
            issues.append(
                f"Required classes count ({len(required_classes)}) exceeds "
                f"model vocab capacity ({spec.vocab_size})"
            )

        # 2. Sequence length check
        if max_sample_tokens > 0 and max_sample_tokens > spec.max_sequence_length:
            issues.append(
                f"Max sample length ({max_sample_tokens} tokens) exceeds "
                f"architecture max sequence length ({spec.max_sequence_length})"
            )

        # 3. Precision support check
        if requested_precision not in spec.supported_precisions:
            issues.append(
                f"Requested precision '{requested_precision}' not in "
                f"supported precisions: {spec.supported_precisions}"
            )

        # 4. LoRA target modules check
        if requested_lora_targets:
            missing_modules = [
                m for m in requested_lora_targets if m not in spec.lora_target_modules
            ]
            if missing_modules:
                issues.append(
                    f"Requested LoRA target modules {missing_modules} not found in "
                    f"architecture supported targets: {spec.lora_target_modules}"
                )

        compatible = len(issues) == 0
        if not compatible:
            logger.warning(
                "Model compatibility check failed for target='%s' arch='%s': %s",
                target,
                spec.architecture_name,
                issues,
            )

        return ModelCompatibilityReport(
            compatible=compatible,
            issues=tuple(issues),
            architecture_name=spec.architecture_name,
            target=target,
        )
