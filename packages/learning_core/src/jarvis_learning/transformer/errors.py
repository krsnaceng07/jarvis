"""Custom exceptions for the JARVIS Transformer Engine."""

from __future__ import annotations


class TransformerError(Exception):
    """Base exception for all Transformer errors."""


class DimensionMismatchError(TransformerError):
    """Raised when tensor dimensions violate architecture invariants."""


class TokenizerError(TransformerError):
    """Raised when encoding or decoding tokens fails."""


class CheckpointCompatibilityError(TransformerError):
    """Raised when a checkpoint fails architectural or schema compatibility checks."""


class ResourceBudgetExceededError(TransformerError):
    """Raised when parameter count or memory usage exceeds resource caps."""


class GradientCheckFailedError(TransformerError):
    """Raised when numerical gradient check discrepancy exceeds tolerance."""


class AbstentionTriggered(TransformerError):
    """Raised or returned when model abstains from prediction due to safety/OOD/confidence gates."""
