"""src.agents.self_healing.last_verified_state — Real-state checkpointing and tracking.

OpenClaw parity: mirrors session-store checkpointing and restart recovery.
Ensures that only verified real-world operations are recognized as completed,
enabling accurate truthful escalation and rollback when tasks are interrupted.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class VerifiedActionRecord:
    """Record of an action verified against physical operating system state."""

    action_id: str
    timestamp: float
    tool_name: str
    target_resource: str
    step_summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LastVerifiedState:
    """Tracks and checkpoints verified physical system state across agent turns."""

    def __init__(self, session_key: str = "desktop:hud") -> None:
        self.session_key = session_key
        self._lock = threading.Lock()
        self._records: list[VerifiedActionRecord] = []
        self._checkpoints: dict[str, int] = {}  # checkpoint_id -> index in _records

    def record_verified_action(
        self,
        tool_name: str,
        target_resource: str,
        step_summary: str,
        details: dict[str, Any] | None = None,
    ) -> VerifiedActionRecord:
        """Record an action whose physical effect was confirmed by ExecutionVerifier."""
        record = VerifiedActionRecord(
            action_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            tool_name=tool_name,
            target_resource=target_resource,
            step_summary=step_summary,
            details=details or {},
        )
        with self._lock:
            self._records.append(record)
        return record

    def get_completed_steps(self) -> list[str]:
        """Return human-readable summaries of all verified operations."""
        with self._lock:
            return [r.step_summary for r in self._records if r.step_summary]

    def get_last_checkpoint(self) -> VerifiedActionRecord | None:
        """Return the most recent verified action record."""
        with self._lock:
            return self._records[-1] if self._records else None

    def create_checkpoint(self, label: str = "checkpoint") -> str:
        """Create a named recovery checkpoint at the current verified record index."""
        cp_id = f"{label}_{int(time.time())}_{str(uuid.uuid4())[:4]}"
        with self._lock:
            self._checkpoints[cp_id] = len(self._records)
        return cp_id

    def rollback_to_checkpoint(self, checkpoint_id: str) -> list[VerifiedActionRecord]:
        """Roll back state records to the designated checkpoint index."""
        with self._lock:
            idx = self._checkpoints.get(checkpoint_id)
            if idx is None:
                return []
            rolled_back = self._records[idx:]
            self._records = self._records[:idx]
            return rolled_back

    def reset(self) -> None:
        """Clear all verified records for a new session."""
        with self._lock:
            self._records.clear()
            self._checkpoints.clear()


__all__ = [
    "LastVerifiedState",
    "VerifiedActionRecord",
]
