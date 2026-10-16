"""jarvis.application_automation.action_verifier — Action verification precedence.

Mirrors OpenClaw's mutation contract in ``src/agents/tools/computer-tool-guidance.ts``:
"Result precedence is `effect: "confirmed"` > `unverifiable` > `suspected_noop`;
action evidence alone does not prove the user's goal. Re-observe before another
mutation, and never blind-retry a mutation."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ActionEffect(str, Enum):
    """Precedence hierarchy for mutation action verification."""

    CONFIRMED = "confirmed"
    UNVERIFIABLE = "unverifiable"
    SUSPECTED_NOOP = "suspected_noop"


@dataclass(slots=True)
class ActionVerificationResult:
    """Outcome of verifying an action's effect on application state."""

    effect: ActionEffect
    action_name: str
    verified: bool
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def confirmed(
        cls, action_name: str, details: Optional[Dict[str, Any]] = None
    ) -> ActionVerificationResult:
        return cls(
            effect=ActionEffect.CONFIRMED,
            action_name=action_name,
            verified=True,
            details=details or {},
        )

    @classmethod
    def unverifiable(
        cls, action_name: str, reason: str, details: Optional[Dict[str, Any]] = None
    ) -> ActionVerificationResult:
        merged = dict(details or {})
        merged["reason"] = reason
        return cls(
            effect=ActionEffect.UNVERIFIABLE,
            action_name=action_name,
            verified=False,
            details=merged,
        )

    @classmethod
    def suspected_noop(
        cls, action_name: str, reason: str, details: Optional[Dict[str, Any]] = None
    ) -> ActionVerificationResult:
        merged = dict(details or {})
        merged["reason"] = reason
        return cls(
            effect=ActionEffect.SUSPECTED_NOOP,
            action_name=action_name,
            verified=False,
            details=merged,
            error=reason,
        )
