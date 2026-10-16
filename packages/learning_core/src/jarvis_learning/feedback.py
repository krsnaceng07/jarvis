"""jarvis_learning.feedback — explicit and implicit feedback collection.

Feedback is the primary signal that tells the learning system whether
an interaction was successful, needs correction, or should be avoided
in the future.  Explicit feedback comes from the user; implicit
feedback is inferred from interaction patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from .experience import generate_id, now_ms

logger = logging.getLogger(__name__)


# Supported signal values — kept as a type alias for documentation.
# Explicit: thumbs_up, thumbs_down, correct, incorrect, user_correction
# Implicit: retry, task_success, task_failure, tool_success, tool_failure,
#           repeated_request, immediate_correction, verification_passed,
#           verification_failed
FeedbackSignal = str


@dataclass(frozen=True, slots=True)
class Feedback:
    """A single feedback record tied to an experience."""

    id: str
    experience_id: str
    created_at: int
    feedback_type: Literal["explicit", "implicit"]
    signal: str
    value: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for SQLite storage."""
        return {
            "id": self.id,
            "experience_id": self.experience_id,
            "created_at": self.created_at,
            "feedback_type": self.feedback_type,
            "signal": self.signal,
            "value": self.value,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Feedback:
        """Deserialize from a SQLite row dict."""
        return cls(
            id=data["id"],
            experience_id=data.get("experience_id", ""),
            created_at=data["created_at"],
            feedback_type=data.get("feedback_type", "implicit"),
            signal=data.get("signal", ""),
            value=data.get("value", ""),
            confidence=float(data.get("confidence", 1.0)),
        )


class FeedbackCollector:
    """Collects and queries feedback records for experiences."""

    def __init__(self) -> None:
        self._feedback: list[Feedback] = []

    def record_explicit(self, experience_id: str, signal: str, value: str = "") -> Feedback:
        """Record explicit user feedback (high confidence)."""
        fb = Feedback(
            id=generate_id(),
            experience_id=experience_id,
            created_at=now_ms(),
            feedback_type="explicit",
            signal=signal,
            value=value,
            confidence=1.0,
        )
        self._feedback.append(fb)
        logger.info(
            "explicit feedback recorded: exp=%s signal=%s",
            experience_id,
            signal,
        )
        return fb

    def record_implicit(
        self,
        experience_id: str,
        signal: str,
        value: str = "",
        confidence: float = 0.5,
    ) -> Feedback:
        """Record implicit feedback inferred from patterns."""
        fb = Feedback(
            id=generate_id(),
            experience_id=experience_id,
            created_at=now_ms(),
            feedback_type="implicit",
            signal=signal,
            value=value,
            confidence=max(0.0, min(1.0, confidence)),
        )
        self._feedback.append(fb)
        logger.debug(
            "implicit feedback recorded: exp=%s signal=%s conf=%.2f",
            experience_id,
            signal,
            fb.confidence,
        )
        return fb

    def get_feedback_for(self, experience_id: str) -> list[Feedback]:
        """Return all feedback for a specific experience."""
        return [f for f in self._feedback if f.experience_id == experience_id]

    def get_all(self) -> list[Feedback]:
        """Return all collected feedback."""
        return list(self._feedback)

    def load(self, feedback_list: list[Feedback]) -> None:
        """Bulk-load feedback records (e.g. from SQLite on startup)."""
        self._feedback.extend(feedback_list)
        logger.info("loaded %d feedback records", len(feedback_list))

    def clear(self) -> None:
        """Clear all in-memory feedback."""
        self._feedback.clear()


class ImplicitFeedbackDetector:
    """Detects implicit feedback signals from interaction patterns."""

    _CORRECTION_PREFIXES = (
        "no ",
        "no,",
        "wrong",
        "incorrect",
        "not that",
        "i said",
        "i meant",
        "that's wrong",
        "thats wrong",
        "actually",
        "i wanted",
        "try again",
        "do it again",
        "redo",
        "fix",
    )

    def detect_repeated_request(self, current_input: str, previous_inputs: list[str]) -> bool:
        """Detect if the user is repeating a request.

        Uses simple token overlap — if >80% of tokens match any
        recent input, it's considered a repeat.
        """
        if not current_input or not previous_inputs:
            return False

        current_tokens = set(current_input.lower().split())
        if not current_tokens:
            return False

        for prev in previous_inputs[-5:]:
            prev_tokens = set(prev.lower().split())
            if not prev_tokens:
                continue
            overlap = current_tokens & prev_tokens
            larger = max(len(current_tokens), len(prev_tokens))
            if larger > 0 and len(overlap) / larger > 0.8:
                return True
        return False

    def detect_immediate_correction(self, messages: list[dict[str, Any]]) -> bool:
        """Detect if the last user message looks like a correction.

        Checks the last user-role message for correction-indicating
        prefixes.
        """
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = str(msg.get("content", "")).strip().lower()
                return any(content.startswith(prefix) for prefix in self._CORRECTION_PREFIXES)
        return False

    def detect_tool_outcome(self, tool_result: dict[str, Any]) -> str:
        """Infer tool_success or tool_failure from a tool result dict."""
        if tool_result.get("is_err") or tool_result.get("error"):
            return "tool_failure"

        if tool_result.get("is_ok") or tool_result.get("success"):
            return "tool_success"

        # Check string content for failure indicators
        result_str = str(tool_result.get("value", tool_result.get("content", "")))
        failure_words = ("error", "failed", "exception", "timeout", "denied")
        if any(w in result_str.lower() for w in failure_words):
            return "tool_failure"

        return "tool_success"
