"""jarvis.desktop_automation.core.action_contract — Action contracts and effect verification.

OpenClaw parity: Defines typed desktop action envelopes and mutation effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ActionEffect(str, Enum):
    CONFIRMED = "confirmed"
    UNVERIFIABLE = "unverifiable"
    SUSPECTED_NOOP = "suspected_noop"


@dataclass(slots=True)
class DesktopAction:
    action_type: str
    application: str
    target: Dict[str, Any] = field(default_factory=dict)
    arguments: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    action_id: Optional[str] = None
    requires_confirmation: bool = False
    risk_level: str = "read_only"  # read_only, local_mutation, external_side_effect
    expected_result: Optional[str] = None


@dataclass(slots=True)
class ActionVerificationResult:
    effect: ActionEffect
    verified: bool
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def confirmed(cls, details: Optional[Dict[str, Any]] = None) -> ActionVerificationResult:
        return cls(effect=ActionEffect.CONFIRMED, verified=True, details=details or {})

    @classmethod
    def unverifiable(cls, reason: str, details: Optional[Dict[str, Any]] = None) -> ActionVerificationResult:
        det = dict(details or {})
        det["reason"] = reason
        return cls(effect=ActionEffect.UNVERIFIABLE, verified=False, details=det, error=reason)

    @classmethod
    def suspected_noop(cls, reason: str, details: Optional[Dict[str, Any]] = None) -> ActionVerificationResult:
        det = dict(details or {})
        det["reason"] = reason
        return cls(effect=ActionEffect.SUSPECTED_NOOP, verified=False, details=det, error=reason)


@dataclass(slots=True)
class DesktopActionResult:
    ok: bool
    action: str
    application: str
    effect: ActionEffect = ActionEffect.UNVERIFIABLE
    verified: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    output_text: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
