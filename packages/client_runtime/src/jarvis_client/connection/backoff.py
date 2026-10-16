"""Bounded exponential backoff with jitter for Track 3.5 connection resilience.

Enforces hard policy:
- Base delay: 250ms
- Max delay: 30s
- Jitter: ±20%
- Status-aware: 401/403 fatal halt, 429 Retry-After compliance, 5xx backoff.
"""

from __future__ import annotations

import random
from typing import Final

BASE_DELAY_SECONDS: Final[float] = 0.25  # 250 ms
MAX_DELAY_SECONDS: Final[float] = 30.0  # 30 s
JITTER_RATIO: Final[float] = 0.20  # ±20%


class BackoffPolicy:
    """Computes bounded exponential backoff delays with randomized jitter."""

    def __init__(
        self,
        base_delay: float = BASE_DELAY_SECONDS,
        max_delay: float = MAX_DELAY_SECONDS,
        jitter_ratio: float = JITTER_RATIO,
        max_attempts: int | None = None,
    ) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_ratio = jitter_ratio
        self.max_attempts = max_attempts
        self._attempt = 0

    @property
    def current_attempt(self) -> int:
        return self._attempt

    def next_delay(self, retry_after: float | None = None) -> float:
        """Compute next backoff interval in seconds.

        If server explicitly supplied `Retry-After`, honors it (clamped to max_delay).
        """
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self.max_delay)

        self._attempt += 1
        # Exponential growth: base * 2^(attempt - 1)
        raw_delay = min(self.base_delay * (2 ** (self._attempt - 1)), self.max_delay)

        # Apply ±jitter
        jitter_range = raw_delay * self.jitter_ratio
        jittered = raw_delay + random.uniform(-jitter_range, jitter_range)
        return max(0.05, min(jittered, self.max_delay))

    def should_retry(self, status_code: int | None = None) -> bool:
        """Evaluate whether retry is permissible for a given error code."""
        # 401 Unauthorized or 403 Forbidden: do not retry blindly
        if status_code in (401, 403, -32001, -32002):
            return False
        # Protocol incompatibility: do not retry
        if status_code == -32014:
            return False
        if self.max_attempts is not None and self._attempt >= self.max_attempts:
            return False
        return True

    def reset(self) -> None:
        """Reset attempt counter upon successful connection."""
        self._attempt = 0


__all__ = ["BASE_DELAY_SECONDS", "MAX_DELAY_SECONDS", "JITTER_RATIO", "BackoffPolicy"]
