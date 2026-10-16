"""RecoveryLoopDetector preventing infinite failure-retry cycles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from jarvis_agent.orchestration.recovery.retry import FailureClass


@dataclass(frozen=True, slots=True)
class LoopDetectionResult:
    """Outcome of failure fingerprint loop detection."""

    is_loop: bool
    fingerprint: str
    occurrences: int
    threshold: int
    message: str


class RecoveryLoopDetector:
    """Detects repeating failure patterns and halts automatic recovery loops."""

    def __init__(self, max_occurrences: int = 3) -> None:
        self._threshold = max_occurrences
        self._history: dict[str, int] = {}

    def compute_fingerprint(
        self,
        node_id: str,
        arguments: dict[str, Any],
        failure_class: FailureClass,
    ) -> str:
        """Derive deterministic hash representing the exact execution failure context."""
        args_json = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        raw = f"{node_id}:{args_json}:{failure_class.value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def record_and_check(
        self,
        node_id: str,
        arguments: dict[str, Any],
        failure_class: FailureClass,
    ) -> LoopDetectionResult:
        """Record an observed failure and check if it exceeds the loop threshold."""
        fp = self.compute_fingerprint(node_id, arguments, failure_class)
        count = self._history.get(fp, 0) + 1
        self._history[fp] = count

        is_loop = count >= self._threshold
        msg = (
            f"Failure fingerprint {fp[:12]} occurred {count} times (threshold {self._threshold}). "
            "Halting automatic recovery loop."
            if is_loop
            else f"Failure count {count}/{self._threshold} for fingerprint {fp[:12]}."
        )

        return LoopDetectionResult(
            is_loop=is_loop,
            fingerprint=fp,
            occurrences=count,
            threshold=self._threshold,
            message=msg,
        )

    def reset_for_task(self) -> None:
        """Clear recorded history."""
        self._history.clear()


__all__ = ["LoopDetectionResult", "RecoveryLoopDetector"]
