"""Multi-Source Feedback Attribution and Bad-Input Isolation.

Ingests implicit, explicit, and execution readback signals.
Critically isolates user input defects (e.g., typos in target paths, non-existent URLs,
unclear instructions) from agent operational failures, preventing the learning engine
from penalizing valid strategies for malformed user inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from jarvis_learning.evidence_model import EvidenceTrustLevel


class FeedbackSourceType(str, Enum):
    IMPLICIT = "implicit"  # User re-prompt, undo, abort, immediate follow-up correction
    EXPLICIT = "explicit"  # Thumbs down, rating, "that didn't work"
    EXECUTION_READBACK = "readback"  # Verifier state checks, filesystem stat, OS exit codes


class AttributionCategory(str, Enum):
    AGENT_EXECUTION_FAILURE = "agent_execution_failure"  # Genuine execution defect
    USER_INPUT_DEFECT = "user_input_defect"  # Malformed prompt, invalid path, contradictory request
    ENVIRONMENT_FAILURE = "environment_failure"  # Transient net/hardware/lock issue
    VERIFIED_SUCCESS = "verified_success"  # Operation succeeded
    AMBIGUOUS = "ambiguous"  # Unclear attribution


@dataclass(slots=True)
class FeedbackSignal:
    source_type: FeedbackSourceType
    raw_payload: Dict[str, Any]
    trust_level: EvidenceTrustLevel
    timestamp: float
    user_sentiment_negative: bool = False
    explicit_complaint: Optional[str] = None


@dataclass(slots=True)
class FeedbackAttributionResult:
    category: AttributionCategory
    confidence: float
    explanation: str
    strategy_penalizable: bool  # False if USER_INPUT_DEFECT or ENVIRONMENT_FAILURE


class FeedbackAttributor:
    """Classifies user and system feedback to separate execution defects from input defects."""

    @staticmethod
    def classify(
        user_prompt: str,
        tool_args: Dict[str, Any],
        tool_error: Optional[str],
        verifier_verdict: Optional[str],
        signals: List[FeedbackSignal],
    ) -> FeedbackAttributionResult:
        error_lower = (tool_error or "").lower()
        prompt_lower = (user_prompt or "").lower()

        # 1. Check for User Input Defects (e.g., file not found on initial open, invalid URL, syntax in user prompt)
        input_defect_indicators = [
            "no such file or directory",
            "file not found",
            "path does not exist",
            "invalid url",
            "could not resolve host",
            "malformed expression",
            "unknown user",
        ]

        # Check if the user prompt explicitly supplied the invalid target
        for indicator in input_defect_indicators:
            if indicator in error_lower:
                # If tool_args path/target matches the prompt text, the user likely requested a nonexistent target
                target = str(
                    tool_args.get("path") or tool_args.get("url") or tool_args.get("target") or ""
                )
                if target and (
                    target.lower() in prompt_lower
                    or any(p in target.lower() for p in prompt_lower.split())
                ):
                    return FeedbackAttributionResult(
                        category=AttributionCategory.USER_INPUT_DEFECT,
                        confidence=0.85,
                        explanation=f"Failure caused by non-existent/invalid user-supplied input: {target}",
                        strategy_penalizable=False,
                    )

        # 2. Check for Transient Environment Failures
        env_indicators = [
            "connection reset by peer",
            "timeout waiting for response",
            "device busy",
            "resource temporarily unavailable",
            "etimedout",
            "econnrefused",
        ]
        if any(ind in error_lower for ind in env_indicators):
            return FeedbackAttributionResult(
                category=AttributionCategory.ENVIRONMENT_FAILURE,
                confidence=0.90,
                explanation=f"Transient environment or network failure: {tool_error}",
                strategy_penalizable=False,
            )

        # 3. Check for Verified Success
        if verifier_verdict == "VERIFIED" and not tool_error:
            has_negative_explicit = any(
                s.source_type == FeedbackSourceType.EXPLICIT and s.user_sentiment_negative
                for s in signals
            )
            if not has_negative_explicit:
                return FeedbackAttributionResult(
                    category=AttributionCategory.VERIFIED_SUCCESS,
                    confidence=0.95,
                    explanation="Operation successfully verified with no negative feedback",
                    strategy_penalizable=False,
                )

        # 4. Check for Genuine Agent Execution Defect
        if tool_error or (
            verifier_verdict
            and verifier_verdict.lower() in ("failed", "false_claim", "verified_failure")
        ):
            return FeedbackAttributionResult(
                category=AttributionCategory.AGENT_EXECUTION_FAILURE,
                confidence=0.80,
                explanation=f"Agent execution failure detected: {tool_error or verifier_verdict}",
                strategy_penalizable=True,
            )

        return FeedbackAttributionResult(
            category=AttributionCategory.AMBIGUOUS,
            confidence=0.50,
            explanation="Attribution unclear from available signals",
            strategy_penalizable=False,
        )
