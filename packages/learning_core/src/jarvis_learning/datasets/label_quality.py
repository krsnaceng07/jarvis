"""jarvis_learning.datasets.label_quality — label assessment and failure classification.

Determines whether a tool-choice label is optimal, acceptable,
suboptimal, wrong, or unsafe.  Uses ``FailureType`` to distinguish
environment errors (not the tool's fault) from actual tool
selection errors.

A tool can fail due to a network outage and still be the correct
choice.  This module prevents JARVIS from learning "the tool was
wrong" when the tool was right but the environment was unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..experience import Experience, TaskEpisode
from ..strategies import FailurePattern
from .schema import FailureType, LabelQuality


@dataclass(frozen=True, slots=True)
class LabelAssessment:
    """Assessment of a training label's quality."""

    quality: str  # LabelQuality value
    confidence: float  # 0.0–1.0
    reason: str
    failure_type: str = ""  # FailureType value if applicable
    alternative_actions: tuple[str, ...] = ()


class LabelQualityAssessor:
    """Assesses the quality of a training label from an experience.

    Logic:
    - Verified success + no unnecessary steps + no anti-pattern → optimal
    - Verified success + some unnecessary steps → acceptable
    - Verified success + matches known anti-pattern → suboptimal
    - Wrong tool selected → wrong
    - Wrong arguments → wrong
    - False completion claim → wrong or unsafe
    - Correct tool + external outage → NOT wrong (environment_error)
    - Correct failure handling → potentially optimal
    """

    def assess(
        self,
        exp: Experience,
        episode: TaskEpisode | None = None,
        failure_patterns: list[FailurePattern] | None = None,
    ) -> LabelAssessment:
        """Assess label quality for an experience."""
        if failure_patterns is None:
            failure_patterns = []

        # False completion claim → wrong
        if exp.verification_status == "false_claim":
            return LabelAssessment(
                quality=LabelQuality.WRONG,
                confidence=0.9,
                reason="false completion claim detected",
                failure_type=FailureType.FALSE_COMPLETION,
            )

        # Classify failure type if the experience failed
        if not exp.success:
            return self._assess_failure(exp, episode, failure_patterns)

        # Success path
        return self._assess_success(exp, episode, failure_patterns)

    def _assess_failure(
        self,
        exp: Experience,
        episode: TaskEpisode | None,
        failure_patterns: list[FailurePattern],
    ) -> LabelAssessment:
        """Assess a failed experience — failure type matters."""
        ft = self._classify_failure_type(exp)

        # Environment/external errors: the tool choice was correct
        if ft in (
            FailureType.ENVIRONMENT_ERROR,
            FailureType.EXTERNAL_SERVICE_ERROR,
        ):
            return LabelAssessment(
                quality=LabelQuality.ACCEPTABLE,
                confidence=0.6,
                reason=(f"tool correct but failed due to {ft.value}; not a tool selection error"),
                failure_type=ft,
            )

        # User input error: not the tool's fault
        if ft == FailureType.USER_INPUT_ERROR:
            return LabelAssessment(
                quality=LabelQuality.UNKNOWN,
                confidence=0.4,
                reason="failure caused by user input, not tool selection",
                failure_type=ft,
            )

        # Tool selection or argument error → wrong
        if ft in (
            FailureType.TOOL_SELECTION_ERROR,
            FailureType.TOOL_ARGUMENT_ERROR,
        ):
            alternatives = self._find_alternatives(exp, failure_patterns)
            return LabelAssessment(
                quality=LabelQuality.WRONG,
                confidence=0.8,
                reason=f"tool {ft.value}: {exp.error or exp.failure_type}",
                failure_type=ft,
                alternative_actions=alternatives,
            )

        # Recovery error
        if ft == FailureType.RECOVERY_ERROR:
            return LabelAssessment(
                quality=LabelQuality.WRONG,
                confidence=0.7,
                reason="failed to recover from earlier error",
                failure_type=ft,
            )

        # False completion
        if ft == FailureType.FALSE_COMPLETION:
            return LabelAssessment(
                quality=LabelQuality.WRONG,
                confidence=0.9,
                reason="claimed success but tool result indicates failure",
                failure_type=ft,
            )

        # Generic failure
        return LabelAssessment(
            quality=LabelQuality.UNKNOWN,
            confidence=0.3,
            reason="unclassified failure",
        )

    def _assess_success(
        self,
        exp: Experience,
        episode: TaskEpisode | None,
        failure_patterns: list[FailurePattern],
    ) -> LabelAssessment:
        """Assess a successful experience."""
        # Check for anti-pattern match
        anti_pattern = self._check_anti_patterns(exp, failure_patterns)
        if anti_pattern:
            return LabelAssessment(
                quality=LabelQuality.SUBOPTIMAL,
                confidence=0.7,
                reason=f"matches known anti-pattern: {anti_pattern}",
                alternative_actions=(anti_pattern,),
            )

        # Check for unnecessary steps
        if episode and episode.unnecessary_steps > 0:
            return LabelAssessment(
                quality=LabelQuality.ACCEPTABLE,
                confidence=0.7,
                reason=(
                    f"{episode.unnecessary_steps} unnecessary step(s) out of {episode.total_steps}"
                ),
            )

        # Check verification status
        if exp.verification_status == "verified_success":
            return LabelAssessment(
                quality=LabelQuality.OPTIMAL,
                confidence=0.9,
                reason="verified success with no unnecessary steps",
            )

        # Unverified success — lower confidence
        return LabelAssessment(
            quality=LabelQuality.ACCEPTABLE,
            confidence=0.5,
            reason="success but outcome not independently verified",
        )

    def _classify_failure_type(self, exp: Experience) -> FailureType:
        """Classify why a tool call failed."""
        error = (exp.error or "").lower()
        failure = (exp.failure_type or "").lower()
        combined = error + " " + failure

        # False completion
        if exp.verification_status == "false_claim":
            return FailureType.FALSE_COMPLETION

        # Environment errors
        env_indicators = [
            "permission denied",
            "access denied",
            "not found",
            "no such file",
            "directory not found",
            "application not running",
            "not installed",
        ]
        if any(ind in combined for ind in env_indicators):
            return FailureType.ENVIRONMENT_ERROR

        # External service errors
        ext_indicators = [
            "timeout",
            "connection refused",
            "network",
            "service unavailable",
            "503",
            "502",
            "500",
            "rate limit",
            "quota exceeded",
        ]
        if any(ind in combined for ind in ext_indicators):
            return FailureType.EXTERNAL_SERVICE_ERROR

        # Tool argument errors
        arg_indicators = [
            "invalid argument",
            "missing required",
            "type error",
            "invalid parameter",
            "bad request",
            "invalid value",
        ]
        if any(ind in combined for ind in arg_indicators):
            return FailureType.TOOL_ARGUMENT_ERROR

        # User input errors
        input_indicators = [
            "invalid input",
            "ambiguous",
            "unclear",
            "cannot parse",
        ]
        if any(ind in combined for ind in input_indicators):
            return FailureType.USER_INPUT_ERROR

        # Default: tool selection error
        return FailureType.TOOL_SELECTION_ERROR

    @staticmethod
    def _check_anti_patterns(
        exp: Experience,
        failure_patterns: list[FailurePattern],
    ) -> str:
        """Check if a successful experience matches a known anti-pattern."""
        if not exp.selected_tool or not failure_patterns:
            return ""
        for pattern in failure_patterns:
            if exp.selected_tool in pattern.bad_action:
                return pattern.preferred_action
        return ""

    @staticmethod
    def _find_alternatives(
        exp: Experience,
        failure_patterns: list[FailurePattern],
    ) -> tuple[str, ...]:
        """Find alternative actions from failure patterns."""
        alternatives: list[str] = []
        for pattern in failure_patterns:
            if (
                exp.selected_tool
                and exp.selected_tool in pattern.bad_action
                and pattern.preferred_action
            ):
                alternatives.append(pattern.preferred_action)
        return tuple(alternatives[:3])
