"""src.infra.retry_policy — request retry policy with backoff, jitter, and retry-after support.

OpenClaw parity: mirrors
``openclaw-main/src/infra/retry-policy.ts``,
``openclaw-main/src/infra/retry-after.ts``, and
``openclaw-main/src/infra/retry.ts``.

Features:
- `retry_async`: Executes an async operation with exponential backoff and jitter.
- `CHANNEL_API_RETRY_DEFAULTS`: 3 attempts, min delay (400-500ms), max delay 30,000ms, 0.1 (10%) jitter.
- `parse_retry_after_header_seconds`: Parses HTTP `Retry-After` header as seconds or HTTP date.
- Model SDK retry limit (`x-should-retry: false` injection when wait > 60 seconds or `JARVIS_SDK_RETRY_MAX_WAIT_SECONDS`).
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

CHANNEL_API_RETRY_REGEX = re.compile(
    r"429|421|timeout|connect|reset|closed|unavailable|temporarily|misdirected request",
    re.IGNORECASE,
)

DEFAULT_SDK_RETRY_MAX_WAIT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class RetryConfig:
    attempts: int = 3
    min_delay_ms: float = 400.0
    max_delay_ms: float = 30_000.0
    jitter: float = 0.1


CHANNEL_API_RETRY_DEFAULTS = RetryConfig(
    attempts=3,
    min_delay_ms=400.0,
    max_delay_ms=30_000.0,
    jitter=0.1,
)

DISCORD_API_RETRY_DEFAULTS = RetryConfig(
    attempts=3,
    min_delay_ms=500.0,
    max_delay_ms=30_000.0,
    jitter=0.1,
)

TELEGRAM_API_RETRY_DEFAULTS = RetryConfig(
    attempts=3,
    min_delay_ms=400.0,
    max_delay_ms=30_000.0,
    jitter=0.1,
)


def parse_retry_after_header_seconds(
    value: str | None,
    now: float | None = None,
) -> float | None:
    """Parse an HTTP ``Retry-After`` header value into delay seconds.

    Mirrors ``parseRetryAfterHeaderSeconds`` (``infra/retry-after.ts``).
    """
    if not value or not isinstance(value, str):
        return None

    trimmed = value.strip()
    if trimmed.isdigit():
        return max(0.0, float(trimmed))

    # HTTP-date parsing fallback
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(trimmed)
        curr_now = now if now is not None else time.time()
        diff = dt.timestamp() - curr_now
        return max(0.0, diff)
    except Exception:
        return None


def extract_retry_after_ms(err: Any) -> float | None:
    """Extract platform-specific ``retry_after`` delay in milliseconds from an error object.

    Handles Telegram `parameters.retry_after` and Discord `retry_after`.
    """
    if not err:
        return None

    # Direct attribute or dict lookup
    candidate = None
    if isinstance(err, dict):
        candidate = (
            err.get("retry_after")
            or (err.get("parameters") or {}).get("retry_after")
            or ((err.get("response") or {}).get("parameters") or {}).get("retry_after")
        )
    elif hasattr(err, "parameters") and hasattr(err.parameters, "retry_after"):
        candidate = err.parameters.retry_after
    elif hasattr(err, "retry_after"):
        candidate = getattr(err, "retry_after")

    if isinstance(candidate, (int, float)) and math.isfinite(candidate):
        return float(candidate) * 1000.0

    return None


def calculate_backoff_delay(
    attempt: int,
    config: RetryConfig,
    retry_after_ms: float | None = None,
) -> float:
    """Calculate backoff delay in milliseconds with jitter and max cap."""
    if retry_after_ms is not None and retry_after_ms > 0:
        base_delay = retry_after_ms
    else:
        # Exponential backoff: min_delay * 2^(attempt - 1)
        base_delay = config.min_delay_ms * (2 ** (attempt - 1))

    # Apply max cap
    capped_delay = min(config.max_delay_ms, base_delay)

    # Apply jitter (e.g. 10%)
    if config.jitter > 0:
        jitter_delta = capped_delay * config.jitter
        capped_delay += random.uniform(-jitter_delta, jitter_delta)

    return max(0.0, capped_delay)


def get_sdk_retry_max_wait_seconds() -> float | None:
    """Get max allowed SDK retry wait seconds from env `JARVIS_SDK_RETRY_MAX_WAIT_SECONDS` or `OPENCLAW_SDK_RETRY_MAX_WAIT_SECONDS`.

    Returns None if disabled via '0', 'false', 'off', 'none', or 'disabled'.
    """
    env_val = os.getenv("JARVIS_SDK_RETRY_MAX_WAIT_SECONDS") or os.getenv("OPENCLAW_SDK_RETRY_MAX_WAIT_SECONDS")
    if not env_val:
        return DEFAULT_SDK_RETRY_MAX_WAIT_SECONDS

    val = env_val.strip().lower()
    if val in ("0", "false", "off", "none", "disabled"):
        return None

    try:
        return float(val)
    except ValueError:
        return DEFAULT_SDK_RETRY_MAX_WAIT_SECONDS


def should_inject_x_should_retry_false(retry_after_seconds: float) -> bool:
    """Return True if ``x-should-retry: false`` should be injected to force fast failover."""
    max_wait = get_sdk_retry_max_wait_seconds()
    if max_wait is None:
        return False
    return retry_after_seconds > max_wait


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    config: RetryConfig = CHANNEL_API_RETRY_DEFAULTS,
    should_retry: Callable[[Exception], bool] | None = None,
    label: str | None = None,
) -> T:
    """Execute async operation *fn* with retries, exponential backoff, and jitter.

    Mirrors ``retryAsync`` (``infra/retry.ts``).
    """
    attempt = 1
    last_err: Exception | None = None

    while True:
        try:
            return await fn()
        except Exception as err:
            last_err = err
            if attempt >= config.attempts:
                raise last_err from None

            # Determine whether error is retryable
            is_retryable = False
            if should_retry:
                is_retryable = should_retry(err)
            else:
                is_retryable = bool(CHANNEL_API_RETRY_REGEX.search(str(err)))

            if not is_retryable:
                raise last_err from None

            # Calculate delay
            retry_after = extract_retry_after_ms(err)
            delay_ms = calculate_backoff_delay(attempt, config, retry_after)

            await asyncio.sleep(delay_ms / 1000.0)
            attempt += 1


__all__ = [
    "CHANNEL_API_RETRY_DEFAULTS",
    "CHANNEL_API_RETRY_REGEX",
    "DEFAULT_SDK_RETRY_MAX_WAIT_SECONDS",
    "DISCORD_API_RETRY_DEFAULTS",
    "RetryConfig",
    "TELEGRAM_API_RETRY_DEFAULTS",
    "calculate_backoff_delay",
    "extract_retry_after_ms",
    "get_sdk_retry_max_wait_seconds",
    "parse_retry_after_header_seconds",
    "retry_async",
    "should_inject_x_should_retry_false",
]
