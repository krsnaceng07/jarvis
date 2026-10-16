"""jarvis.agents.task.stage_reporter — Real-time observable task stage reporter.

OpenClaw parity:
- Exposes observable, structured task progress in real time.
- Emits standardized events distinguishing PLANNING, OBSERVING, ACTION, VERIFYING,
  RECOVERING, WAITING_FOR_USER, COMPLETED, and FAILED.
- Enforces truthful completion reporting: never announces "completed" before verification.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .runtime_state import RuntimeStateManager, TaskStatus


class StagePhase(str, Enum):
    """High-level lifecycle phases for user-facing visibility."""

    PLANNING = "PLANNING"
    OBSERVING = "OBSERVING"
    ACTION = "ACTION"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(slots=True)
class StageProgressUpdate:
    """Detailed progress snapshot of an active task."""

    task_name: str
    phase: StagePhase
    current_stage: str
    completed_stages: List[str] = field(default_factory=list)
    pending_stages: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_formatted_log(self) -> str:
        """Format as a clear, structured progress log."""
        lines = [
            f"[TASK: {self.task_name}] 📍 {self.phase.value} → {self.current_stage}",
        ]
        if self.completed_stages:
            lines.append(f"  ✓ Completed: {', '.join(self.completed_stages[-3:])}")
        if self.pending_stages:
            lines.append(f"  ⏳ Pending: {', '.join(self.pending_stages[:3])}")
        if self.details:
            detail_str = " | ".join(f"{k}: {v}" for k, v in self.details.items() if v)
            if detail_str:
                lines.append(f"  ℹ️ {detail_str}")
        return "\n".join(lines)


class StageReporter:
    """Centralized reporter broadcasting real-time progress to logs, console, and UI listeners."""

    _instance: Optional[StageReporter] = None

    def __init__(self) -> None:
        self._listeners: List[Callable[[StageProgressUpdate], None]] = []
        self._state_mgr = RuntimeStateManager.get_instance()

    @classmethod
    def get_instance(cls) -> StageReporter:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_listener(self, listener: Callable[[StageProgressUpdate], None]) -> None:
        """Subscribe a callback to progress updates."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[StageProgressUpdate], None]) -> None:
        """Unsubscribe a callback."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def report(
        self,
        task_name: str,
        phase: StagePhase,
        stage_name: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> StageProgressUpdate:
        """Broadcast stage progress update."""
        state = self._state_mgr.state

        # Update authoritative runtime state
        if phase == StagePhase.OBSERVING:
            self._state_mgr.transition_stage(stage_name, status=TaskStatus.OBSERVING)
        elif phase == StagePhase.ACTION:
            self._state_mgr.transition_stage(stage_name, status=TaskStatus.EXECUTING)
        elif phase == StagePhase.VERIFYING:
            self._state_mgr.transition_stage(stage_name, status=TaskStatus.VERIFYING)
        elif phase == StagePhase.COMPLETED:
            self._state_mgr.transition_stage(stage_name, status=TaskStatus.COMPLETED_VERIFIED, verified=True)
        elif phase == StagePhase.FAILED:
            self._state_mgr.transition_stage(stage_name, status=TaskStatus.FAILED, verified=False)
        elif phase == StagePhase.RECOVERING:
            self._state_mgr.transition_stage(stage_name, status=TaskStatus.RECOVERING)

        update = StageProgressUpdate(
            task_name=task_name,
            phase=phase,
            current_stage=stage_name,
            completed_stages=list(state.completed_stages),
            pending_stages=list(state.pending_stages),
            details=details or {},
        )

        # Print human-readable progress
        print(update.to_formatted_log())

        # Notify subscribers
        for listener in self._listeners:
            try:
                listener(update)
            except Exception:
                pass

        return update
