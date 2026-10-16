"""src.agents.self_healing.strategies.transient_retry — Transient backoff strategy.

OpenClaw parity: mirrors computeBackoff and RetrySupervisor from packages/retry.
"""

from __future__ import annotations

import asyncio
import random
from typing import Literal

from ..failure_event import ErrorCategory, FailureEvent
from .base import RecoveryResult, RecoveryStrategy


class TransientRetryStrategy(RecoveryStrategy):
    """Handles transient network, rate limits, and 503 errors via backoff with jitter."""

    name: str = "transient_retry"

    def __init__(
        self,
        min_delay_ms: float = 400.0,
        max_delay_ms: float = 30_000.0,
        factor: float = 2.0,
        jitter: float = 0.15,
        jitter_mode: Literal["symmetric", "positive"] = "positive",
    ) -> None:
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.factor = factor
        self.jitter = jitter
        self.jitter_mode = jitter_mode

    async def can_handle(self, event: FailureEvent) -> bool:
        """Handles transient network errors, rate limits, and model overload."""
        return event.category in (
            ErrorCategory.NETWORK_TRANSIENT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.MODEL_OVERLOADED,
        )

    def calculate_delay_sec(self, attempt: int, retry_after_sec: float | None = None) -> float:
        """Calculate delay in seconds with exponential backoff and jitter."""
        if retry_after_sec is not None and retry_after_sec > 0:
            base_delay_ms = retry_after_sec * 1000.0
        else:
            base_delay_ms = self.min_delay_ms * (self.factor ** max(0, attempt - 1))

        capped_ms = min(self.max_delay_ms, base_delay_ms)

        if self.jitter > 0:
            if self.jitter_mode == "positive":
                capped_ms += random.uniform(0, self.jitter * capped_ms)
            else:  # symmetric
                delta = self.jitter * capped_ms
                capped_ms += random.uniform(-delta, delta)

        return max(0.05, capped_ms / 1000.0)

    async def execute(self, event: FailureEvent) -> RecoveryResult:
        """Compute delay and perform sleep for backoff."""
        retry_after = event.context.get("retry_after_sec")
        if retry_after is not None:
            try:
                retry_after = float(retry_after)
            except (ValueError, TypeError):
                retry_after = None

        delay_sec = self.calculate_delay_sec(event.attempt_count, retry_after)
        await asyncio.sleep(delay_sec)

        return RecoveryResult(
            success=True,
            action_taken=f"Backoff sleep ({delay_sec:.2f}s, attempt {event.attempt_count})",
            requires_retry=True,
            backoff_delay_sec=delay_sec,
            details={"attempt": event.attempt_count, "delay_sec": delay_sec},
        )


__all__ = [
    "TransientRetryStrategy",
]
