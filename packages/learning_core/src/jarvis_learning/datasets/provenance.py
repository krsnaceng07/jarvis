"""jarvis_learning.datasets.provenance — strict training approval gates.

Every training sample's provenance is evaluated against hardcoded
safety rules.  User confirmation **never** overrides: secret
detection, poisoning checks, prompt injection, tool-result
contradiction, or malformed samples.

The ``poisoning_check_passed`` field uses explicit ``True`` for pass.
Any other value (``False``, missing, ``None``) is treated as reject.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..experience import Experience


@dataclass(frozen=True, slots=True)
class TrainingSampleProvenance:
    """Provenance metadata attached to every training sample."""

    source_type: str
    # "user_verified" | "tool_verified" | "environment_verified"
    # | "llm_inferred" | "externally_sourced"

    verification_status: str
    # "verified" | "unverified" | "disputed" | "rejected"

    user_feedback: str
    # "positive" | "negative" | "correction" | "none"

    tool_result_verified: bool
    environment_state_verified: bool
    confidence: float
    quality_score: float
    poisoning_check_passed: bool
    cleaner_passed: bool
    contradiction_check_passed: bool
    approved_for_training: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "verification_status": self.verification_status,
            "user_feedback": self.user_feedback,
            "tool_result_verified": self.tool_result_verified,
            "environment_state_verified": self.environment_state_verified,
            "confidence": self.confidence,
            "quality_score": self.quality_score,
            "poisoning_check_passed": self.poisoning_check_passed,
            "cleaner_passed": self.cleaner_passed,
            "contradiction_check_passed": self.contradiction_check_passed,
            "approved_for_training": self.approved_for_training,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrainingSampleProvenance:
        return cls(
            source_type=d.get("source_type", "llm_inferred"),
            verification_status=d.get("verification_status", "unverified"),
            user_feedback=d.get("user_feedback", "none"),
            tool_result_verified=d.get("tool_result_verified", False),
            environment_state_verified=d.get("environment_state_verified", False),
            confidence=d.get("confidence", 0.0),
            quality_score=d.get("quality_score", 0.0),
            poisoning_check_passed=d.get("poisoning_check_passed", False),
            cleaner_passed=d.get("cleaner_passed", False),
            contradiction_check_passed=d.get("contradiction_check_passed", False),
            approved_for_training=d.get("approved_for_training", False),
        )


class ProvenanceEvaluator:
    """Computes provenance and applies strict approval gates.

    Approval rules (hardcoded safety — not configurable):

    user_verified + verified + poisoning_check_passed=True
        + cleaner_passed + no contradiction + quality≥0.7 → approved

    tool_verified + positive feedback + verified + poisoning=True
        + cleaner + quality≥0.7 → approved

    tool_verified only + verified + poisoning=True
        + cleaner + quality≥0.8 → approved

    llm_inferred + any → NEVER approved

    any + poisoning_check_passed is not True → NEVER approved
    any + cleaner_passed is not True → NEVER approved
    any + contradiction → NEVER approved
    any + rejected → NEVER approved
    """

    def evaluate(
        self,
        exp: Experience,
        *,
        cleaner_passed: bool,
        contradiction_free: bool,
        quality_score: float | None = None,
    ) -> TrainingSampleProvenance:
        """Compute provenance for an experience.

        ``cleaner_passed`` and ``contradiction_free`` come from
        upstream pipeline stages that have already run.
        """
        source_type = exp.source_type or "llm_inferred"
        verification_status = self._map_verification(exp.verification_status)
        user_feedback = self._map_feedback(exp.user_feedback)
        tool_verified = exp.verification_status in ("verified_success", "verified_failure")

        # Quality score: use provided or derive from experience
        q_score = quality_score if quality_score is not None else exp.confidence

        # Poisoning check: for now, all Wave 1 experiences pass unless
        # they contain known attack patterns.  The cleaner stage handles
        # the actual detection; here we just propagate the result.
        poisoning_passed = self._check_poisoning(exp)

        # Determine approval
        approved = self._evaluate_approval(
            source_type=source_type,
            verification_status=verification_status,
            user_feedback=user_feedback,
            poisoning_check_passed=poisoning_passed,
            cleaner_passed=cleaner_passed,
            contradiction_free=contradiction_free,
            quality_score=q_score,
        )

        return TrainingSampleProvenance(
            source_type=source_type,
            verification_status=verification_status,
            user_feedback=user_feedback,
            tool_result_verified=tool_verified,
            environment_state_verified=False,
            confidence=exp.confidence,
            quality_score=q_score,
            poisoning_check_passed=poisoning_passed,
            cleaner_passed=cleaner_passed,
            contradiction_check_passed=contradiction_free,
            approved_for_training=approved,
        )

    def _evaluate_approval(
        self,
        *,
        source_type: str,
        verification_status: str,
        user_feedback: str,
        poisoning_check_passed: bool,
        cleaner_passed: bool,
        contradiction_free: bool,
        quality_score: float,
    ) -> bool:
        """Apply the strict approval gate rules.

        Uses explicit ``is not True`` checks so that missing/None/False
        all result in rejection.
        """
        # Hard rejections — never overridden by any source
        if poisoning_check_passed is not True:
            return False
        if cleaner_passed is not True:
            return False
        if not contradiction_free:
            return False
        if verification_status == "rejected":
            return False

        # llm_inferred → NEVER auto-approved
        if source_type == "llm_inferred":
            return False

        # user_verified: strictest gate still applies
        if source_type == "user_verified":
            return verification_status == "verified" and quality_score >= 0.7

        # tool_verified + positive feedback
        if source_type == "tool_verified" and user_feedback == "positive":
            return verification_status == "verified" and quality_score >= 0.7

        # tool_verified only (no user feedback)
        if source_type == "tool_verified":
            return verification_status == "verified" and quality_score >= 0.8

        # environment_verified
        if source_type == "environment_verified":
            return verification_status == "verified" and quality_score >= 0.7

        # externally_sourced
        if source_type == "externally_sourced":
            return verification_status == "verified" and quality_score >= 0.9

        return False

    @staticmethod
    def _map_verification(status: str) -> str:
        """Map Wave 1 verification_status to provenance status."""
        mapping = {
            "verified_success": "verified",
            "verified_failure": "verified",
            "false_claim": "rejected",
            "unverified": "unverified",
        }
        return mapping.get(status, "unverified")

    @staticmethod
    def _map_feedback(feedback: str) -> str:
        """Map Wave 1 user_feedback to provenance feedback."""
        if feedback in ("thumbs_up", "positive", "confirmed"):
            return "positive"
        if feedback in ("thumbs_down", "negative", "incorrect"):
            return "negative"
        if feedback in ("correction", "user_correction"):
            return "correction"
        return "none"

    @staticmethod
    def _check_poisoning(exp: Experience) -> bool:
        """Basic poisoning check on experience content.

        Looks for known attack patterns in user input and tool args.
        The cleaner module does the thorough check; this is a fast
        pre-filter.
        """
        suspicious_patterns = [
            "ignore previous instructions",
            "ignore all prior",
            "disregard your instructions",
            "you are now",
            "new system prompt",
            "override system",
            "jailbreak",
        ]
        text = (exp.user_input + " " + exp.tool_arguments).lower()
        return not any(p in text for p in suspicious_patterns)
