"""jarvis_learning.training.live_governance — Code-Level Permanent Deny for Live Training.

Enforces:
1. INV-GOV-001 / INV-P9-CONFIG-001: Code-level permanent deny for LIVE_TRAINING and PRODUCTION_ACTIVATION.
2. Complete failure-domain isolation: Learning worker failures never terminate or degrade host assistant.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Permanent code-level governance constants
ALLOW_LIVE_TRAINING: bool = False
ALLOW_AUTONOMOUS_PROMOTION: bool = False
ALLOW_PRODUCTION_ACTIVATION: bool = False


class LiveTrainingGovernanceError(PermissionError):
    """Raised whenever live training or autonomous production promotion is attempted."""


def assert_live_training_permanently_denied(attempted_mode: str = "LIVE_TRAINING") -> None:
    """Strictly assert that live training cannot be executed in this runtime."""
    if attempted_mode in ("LIVE_TRAINING", "PRODUCTION_ACTIVATION", "AUTONOMOUS_PROMOTION"):
        msg = f"LIVE_TRAINING is permanently disabled: mode '{attempted_mode}' is rejected by code-level invariant."
        logger.error(msg)
        raise LiveTrainingGovernanceError(msg)
