"""jarvis_learning.truthfulness — Authoritative physical outcome verification and truthful completion enforcement.

Implements the 6-Tier Truthfulness Contract and the 7 canonical outcome classes:
  MODEL = proposes
  TOOL = executes
  OS = reports reality
  VERIFIER = confirms reality
  STATE = records reality
  MODEL = explains reality

Rule: ONLY `VERIFIED_SUCCESS` may permit definitive completion language
("Done", "Completed", "Successfully opened...", "The file was created...").
All other outcomes must produce cautious, accurate, and truthful wording.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Optional


class OutcomeClass(str, enum.Enum):
    """Canonical 7-tier execution outcome classification."""

    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    UNVERIFIED = "UNVERIFIED"
    VERIFIER_ERROR = "VERIFIER_ERROR"
    ENVIRONMENT_UNKNOWN = "ENVIRONMENT_UNKNOWN"
    FAILED = "FAILED"
    POLICY_DENIED = "POLICY_DENIED"


@dataclass(frozen=True, slots=True)
class TruthfulOutcome:
    """Standardized authoritative outcome evaluated against physical reality."""

    outcome_class: OutcomeClass
    verified: bool
    tool_name: str
    target_resource: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    truthful_message: str = ""
    allows_definitive_completion: bool = False


# Phrases that indicate definitive success or completion
_DEFINITIVE_COMPLETION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:done|completed|finished|succeeded|successfully)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:file\s+(?:has\s+been\s+)?created|saved\s+successfully|written\s+to\s+disk)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:successfully\s+(?:opened|launched|deleted|removed|muted|set|closed))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:task\s+(?:is\s+)?complete(?:d)?|all\s+steps\s+done)\b",
        re.IGNORECASE,
    ),
)


class TruthfulCompletionEnforcer:
    """Authoritatively validates execution outcomes and prevents false completions."""

    @staticmethod
    def evaluate_outcome(
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        verifier_outcome: Any = None,
        policy_blocked: bool = False,
        policy_reason: str = "",
        environment_blocked: bool = False,
        environment_reason: str = "",
    ) -> TruthfulOutcome:
        """Classify tool execution outcome into one of the 7 authoritative classes."""
        # 1. Policy blocked
        if policy_blocked:
            reason = policy_reason or "Action was blocked by safety policy"
            return TruthfulOutcome(
                outcome_class=OutcomeClass.POLICY_DENIED,
                verified=False,
                tool_name=tool_name,
                target_resource=str(tool_args.get("path") or tool_args.get("target") or ""),
                error=reason,
                truthful_message=f"Action blocked by policy: {reason}",
                allows_definitive_completion=False,
            )

        # 2. Environment / permission blocked
        if environment_blocked:
            reason = environment_reason or "Host environment or permission probe failed"
            return TruthfulOutcome(
                outcome_class=OutcomeClass.ENVIRONMENT_UNKNOWN,
                verified=False,
                tool_name=tool_name,
                target_resource=str(tool_args.get("path") or tool_args.get("target") or ""),
                error=reason,
                truthful_message=f"Environment state unknown: {reason}",
                allows_definitive_completion=False,
            )

        # 3. Check for explicit tool execution errors (exceptions, error exit codes, error messages)
        result_text = ""
        is_tool_error = False
        tool_error_msg = ""

        if isinstance(tool_result, dict):
            if tool_result.get("is_error") or tool_result.get("error"):
                is_tool_error = True
                tool_error_msg = str(
                    tool_result.get("error") or tool_result.get("message") or "Tool reported error"
                )
            result_text = str(tool_result.get("result") or tool_result.get("output") or "")
        elif isinstance(tool_result, str):
            result_text = tool_result
            low = result_text.lower()
            if (
                low.startswith("error:")
                or "traceback (most recent call last)" in low
                or '"ok": false' in low
            ):
                is_tool_error = True
                tool_error_msg = result_text[:300]
        elif hasattr(tool_result, "error") and tool_result.error:
            is_tool_error = True
            tool_error_msg = str(tool_result.error)

        if is_tool_error:
            return TruthfulOutcome(
                outcome_class=OutcomeClass.FAILED,
                verified=False,
                tool_name=tool_name,
                target_resource=str(tool_args.get("path") or tool_args.get("target") or ""),
                error=tool_error_msg,
                truthful_message=f"Action failed during execution: {tool_error_msg}",
                allows_definitive_completion=False,
            )

        # 4. Check verifier outcome if available
        if verifier_outcome is not None:
            v_status = getattr(verifier_outcome, "status", None) or (
                verifier_outcome.get("status") if isinstance(verifier_outcome, dict) else ""
            )
            v_verified = getattr(verifier_outcome, "verified", False) or (
                verifier_outcome.get("verified", False)
                if isinstance(verifier_outcome, dict)
                else False
            )
            v_error = getattr(verifier_outcome, "error", None) or (
                verifier_outcome.get("error") if isinstance(verifier_outcome, dict) else None
            )
            v_details = getattr(verifier_outcome, "details", {}) or (
                verifier_outcome.get("details", {}) if isinstance(verifier_outcome, dict) else {}
            )

            if v_status == "verifier_error" or (
                v_error and "verification encountered exception" in str(v_error).lower()
            ):
                return TruthfulOutcome(
                    outcome_class=OutcomeClass.VERIFIER_ERROR,
                    verified=False,
                    tool_name=tool_name,
                    target_resource=getattr(verifier_outcome, "target_resource", None),
                    details=v_details,
                    error=str(v_error),
                    truthful_message=f"Verification probe error: {v_error}",
                    allows_definitive_completion=False,
                )

            if v_status in ("partial", "partial_success"):
                return TruthfulOutcome(
                    outcome_class=OutcomeClass.PARTIAL_SUCCESS,
                    verified=False,
                    tool_name=tool_name,
                    target_resource=getattr(verifier_outcome, "target_resource", None),
                    details=v_details,
                    error=str(v_error) if v_error else None,
                    truthful_message="Action partially completed, but remaining stages could not be verified.",
                    allows_definitive_completion=False,
                )

            if v_verified and v_status == "verified":
                return TruthfulOutcome(
                    outcome_class=OutcomeClass.VERIFIED_SUCCESS,
                    verified=True,
                    tool_name=tool_name,
                    target_resource=getattr(verifier_outcome, "target_resource", None),
                    details=v_details,
                    error=None,
                    truthful_message=f"Action verified successfully on host system ({tool_name}).",
                    allows_definitive_completion=True,
                )

            # Verifier reported verification failure
            return TruthfulOutcome(
                outcome_class=OutcomeClass.FAILED,
                verified=False,
                tool_name=tool_name,
                target_resource=getattr(verifier_outcome, "target_resource", None),
                details=v_details,
                error=str(v_error or "Physical postcondition verification failed"),
                truthful_message=f"Physical verification failed: {v_error}",
                allows_definitive_completion=False,
            )

        # 5. If no verifier ran, the action is UNVERIFIED
        return TruthfulOutcome(
            outcome_class=OutcomeClass.UNVERIFIED,
            verified=False,
            tool_name=tool_name,
            target_resource=str(tool_args.get("path") or tool_args.get("target") or ""),
            details={"raw_output": result_text[:200]},
            truthful_message=f"Action executed ({tool_name}), but physical outcome could not be independently verified.",
            allows_definitive_completion=False,
        )

    @staticmethod
    def enforce_completion_truthfulness(
        proposed_message: str,
        outcome: TruthfulOutcome,
    ) -> str:
        """Enforce truthful completion wording on model-generated response text.

        If the model claims definitive completion ("Done", "Successfully created", etc.)
        when the outcome is NOT VERIFIED_SUCCESS, this amends or replaces the claim
        with an authoritative, honest statement of reality.
        """
        if outcome.outcome_class == OutcomeClass.VERIFIED_SUCCESS and outcome.verified:
            return proposed_message

        has_completion_claim = any(
            pattern.search(proposed_message) for pattern in _DEFINITIVE_COMPLETION_PATTERNS
        )

        if outcome.outcome_class == OutcomeClass.POLICY_DENIED:
            return f"Action blocked: {outcome.error or 'Safety policy prevented execution.'}"

        if outcome.outcome_class == OutcomeClass.FAILED:
            return f"Action failed: {outcome.error or 'The requested action encountered an error on the host PC.'}"

        if outcome.outcome_class == OutcomeClass.VERIFIER_ERROR:
            return (
                f"Action outcome unconfirmed: Verification probe encountered an error ({outcome.error}). "
                "Cannot confirm physical success."
            )

        if outcome.outcome_class == OutcomeClass.ENVIRONMENT_UNKNOWN:
            return f"Host state unknown: {outcome.error or 'Environment state could not be inspected.'}"

        if outcome.outcome_class == OutcomeClass.PARTIAL_SUCCESS:
            return "Action partially completed, but subsequent steps could not be verified on the host system."

        if outcome.outcome_class == OutcomeClass.UNVERIFIED:
            if has_completion_claim:
                return (
                    f"Tool was invoked ({outcome.tool_name}), but outcome has not been verified on disk or hardware. "
                    "Cannot confirm completion."
                )
            return proposed_message

        return proposed_message
