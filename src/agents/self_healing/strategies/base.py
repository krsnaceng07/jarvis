"""src.agents.self_healing.strategies.base — Base interfaces for recovery strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..failure_event import FailureEvent


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Outcome of a recovery strategy attempt."""

    success: bool
    action_taken: str
    repaired_args: dict[str, Any] | None = None
    output: str | None = None
    error: str | None = None
    requires_retry: bool = False
    backoff_delay_sec: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class RecoveryStrategy(ABC):
    """Abstract base class for all self-healing recovery strategies."""

    name: str = "base_strategy"

    @abstractmethod
    async def can_handle(self, event: FailureEvent) -> bool:
        """Return True if this strategy can address the failure event."""
        ...

    @abstractmethod
    async def execute(self, event: FailureEvent) -> RecoveryResult:
        """Execute the recovery action."""
        ...


__all__ = [
    "RecoveryResult",
    "RecoveryStrategy",
]
