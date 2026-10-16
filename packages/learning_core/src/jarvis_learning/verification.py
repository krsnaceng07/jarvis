"""jarvis_learning.verification — outcome verification system.

Distinguishes between "LLM claimed success", "tool returned success",
and "environment state actually changed".  Unverified claims never
automatically become positive training samples.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Discriminated outcome of a verification check."""

    status: Literal["verified_success", "verified_failure", "unverified", "false_claim"]
    claimed_outcome: str = ""
    actual_outcome: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5


class OutcomeVerifier(ABC):
    """Base class for outcome verifiers."""

    @abstractmethod
    def verify(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        claimed_outcome: str = "",
    ) -> VerificationResult:
        """Verify whether a tool execution outcome matches claims."""


class ToolResultVerifier(OutcomeVerifier):
    """Checks tool return values for success/failure patterns."""

    _FAILURE_WORDS = re.compile(
        r"\b(error|failed|exception|timeout|denied|refused|not found|"
        r"permission|unauthorized|forbidden|crash|abort)\b",
        re.IGNORECASE,
    )
    _SUCCESS_WORDS = re.compile(
        r"\b(success|completed|done|created|updated|saved|"
        r"opened|navigated|executed|finished)\b",
        re.IGNORECASE,
    )

    def verify(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        claimed_outcome: str = "",
    ) -> VerificationResult:
        """Verify a tool result by inspecting its structure."""
        if isinstance(tool_result, dict):
            return self._verify_dict(tool_result, claimed_outcome)
        if isinstance(tool_result, str):
            return self._verify_string(tool_result, claimed_outcome)
        return VerificationResult(
            status="unverified",
            claimed_outcome=claimed_outcome,
            actual_outcome=str(tool_result)[:200],
            confidence=0.3,
        )

    def _verify_dict(self, result: dict[str, Any], claimed: str) -> VerificationResult:
        if result.get("is_err") or result.get("error"):
            error_msg = str(result.get("error", result.get("message", "")))
            return VerificationResult(
                status="verified_failure",
                claimed_outcome=claimed,
                actual_outcome=f"error: {error_msg[:200]}",
                evidence={"error_key": True},
                confidence=0.9,
            )
        if result.get("is_ok") or result.get("success"):
            value = str(result.get("value", result.get("data", "")))[:200]
            return VerificationResult(
                status="verified_success",
                claimed_outcome=claimed,
                actual_outcome=value,
                evidence={"success_key": True},
                confidence=0.85,
            )
        return self._verify_string(
            str(result.get("value", result.get("content", str(result)))),
            claimed,
        )

    def _verify_string(self, result_text: str, claimed: str) -> VerificationResult:
        has_failure = bool(self._FAILURE_WORDS.search(result_text))
        has_success = bool(self._SUCCESS_WORDS.search(result_text))

        if has_failure and not has_success:
            return VerificationResult(
                status="verified_failure",
                claimed_outcome=claimed,
                actual_outcome=result_text[:200],
                evidence={"pattern": "failure_words"},
                confidence=0.7,
            )
        if has_success and not has_failure:
            return VerificationResult(
                status="verified_success",
                claimed_outcome=claimed,
                actual_outcome=result_text[:200],
                evidence={"pattern": "success_words"},
                confidence=0.65,
            )
        return VerificationResult(
            status="unverified",
            claimed_outcome=claimed,
            actual_outcome=result_text[:200],
            confidence=0.3,
        )


class ClaimVerifier(OutcomeVerifier):
    """Detects LLM claiming actions it didn't actually perform."""

    _COMPLETION_PHRASES = re.compile(
        r"\b(i have|i've|done|completed|set to|changed to|"
        r"opened|created|saved|volume is now|"
        r"successfully|finished|updated)\b",
        re.IGNORECASE,
    )

    def verify(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        claimed_outcome: str = "",
    ) -> VerificationResult:
        """Check if the claimed outcome contradicts the tool result."""
        if not claimed_outcome:
            return VerificationResult(status="unverified", claimed_outcome="", confidence=0.2)

        result_str = str(tool_result) if tool_result is not None else ""
        claims_completion = bool(self._COMPLETION_PHRASES.search(claimed_outcome))
        result_failed = self._result_indicates_failure(result_str, tool_result)

        if claims_completion and result_failed:
            return VerificationResult(
                status="false_claim",
                claimed_outcome=claimed_outcome[:300],
                actual_outcome=result_str[:200],
                evidence={
                    "claim_type": "completion_assertion",
                    "result_failed": True,
                },
                confidence=0.8,
            )

        specific_values = re.findall(r"\b\d+\b", claimed_outcome)
        if specific_values and result_str:
            missing = [v for v in specific_values if v not in result_str]
            if missing and len(missing) == len(specific_values):
                return VerificationResult(
                    status="false_claim",
                    claimed_outcome=claimed_outcome[:300],
                    actual_outcome=result_str[:200],
                    evidence={
                        "claim_type": "specific_value_mismatch",
                        "missing_values": missing[:5],
                    },
                    confidence=0.6,
                )

        return VerificationResult(
            status="unverified",
            claimed_outcome=claimed_outcome[:300],
            actual_outcome=result_str[:200],
            confidence=0.3,
        )

    @staticmethod
    def _result_indicates_failure(result_str: str, raw: Any) -> bool:
        if isinstance(raw, dict):
            if raw.get("is_err") or raw.get("error"):
                return True
        failure_words = ("error", "failed", "exception", "denied", "not found")
        return any(w in result_str.lower() for w in failure_words)


class CompositeVerifier(OutcomeVerifier):
    """Runs multiple verifiers; false_claim takes priority."""

    def __init__(self, verifiers: list[OutcomeVerifier] | None = None) -> None:
        self._verifiers = verifiers or [
            ToolResultVerifier(),
            ClaimVerifier(),
        ]

    def verify(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: Any,
        claimed_outcome: str = "",
    ) -> VerificationResult:
        """Run all sub-verifiers and pick the strongest signal."""
        results: list[VerificationResult] = []
        for v in self._verifiers:
            try:
                results.append(v.verify(tool_name, tool_args, tool_result, claimed_outcome))
            except Exception:
                logger.exception("verifier %s raised", type(v).__name__)

        if not results:
            return VerificationResult(status="unverified", confidence=0.1)

        false_claims = [r for r in results if r.status == "false_claim"]
        if false_claims:
            return max(false_claims, key=lambda r: r.confidence)

        return max(results, key=lambda r: r.confidence)
