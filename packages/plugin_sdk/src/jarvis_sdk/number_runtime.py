"""jarvis_sdk.number_runtime — strict number parsing.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/number-runtime``'s
``parseStrictPositiveInteger``, ``resolveTimerTimeoutMs``,
``asDateTimestampMs``, and ``resolveExpiresAtMsFromDurationMs``.

Used by ``memory-lancedb`` to parse CLI args and to set the
embeddings request timeout, and by ``active-memory`` to build
the recall cache's expiry timestamp.

Architecture
============
OpenClaw has a single module that wraps the strict-positive-int
parser, the timer-timeout resolver, and date-timestamp
helpers. The Python equivalent is the same:
``parse_strict_positive_integer`` raises on garbage input;
``resolve_timer_timeout_ms`` clamps a value to a positive
integer with a fallback; ``as_date_timestamp_ms`` coerces a
value to a finite millisecond timestamp (or ``None`` for
unparseable input); ``resolve_expires_at_ms_from_duration_ms``
adds a duration to a now-ms and returns the resulting
millisecond timestamp (or ``None`` for unparseable input).

Parity
======
- ``parse_strict_positive_integer(value)`` → ``int`` or
  ``None`` (if value is empty/undefined). Raises ``ValueError``
  on negative or non-integer strings.
- ``resolve_timer_timeout_ms(raw, fallback)`` → ``int``
  (clamped to >= 1). Treats ``None``, ``0``, and negative values
  as "use fallback".
- ``as_date_timestamp_ms(value)`` → ``int | None`` (finite
  millisecond timestamp, or ``None`` for ``None``/non-numeric).
- ``resolve_expires_at_ms_from_duration_ms(duration_ms, now_ms)``
  → ``int | None`` (``now_ms + duration_ms`` if both finite).
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime


def parse_strict_positive_integer(value: object) -> int | None:
    """Parse a strict positive integer from a CLI flag or string.

    Returns None for ``None`` / empty string (the "flag not
    provided" case in OpenClaw). Raises ``ValueError`` for
    negative, zero, or non-integer strings.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("expected a positive integer, got bool")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"expected a positive integer, got {value}")
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            parsed = int(trimmed)
        except ValueError as e:
            raise ValueError(f"expected a positive integer, got {value!r}") from e
        if parsed <= 0:
            raise ValueError(f"expected a positive integer, got {parsed}")
        return parsed
    raise ValueError(f"expected a positive integer, got {type(value).__name__}")


def resolve_timer_timeout_ms(raw: int | float | None, fallback: int) -> int:
    """Resolve a timer timeout in ms, clamped to >= 1.

    OpenClaw uses this for embedding request timeouts and similar
    timer arms. We mirror: None / zero / negative values fall
    through to the fallback; positive values are clamped to
    ``>= 1`` ms (a 0ms timer would fire immediately, which is
    never the intent).
    """
    if raw is None or not isinstance(raw, int | float) or raw <= 0:
        return max(1, int(fallback))
    return max(1, int(raw))


def as_date_timestamp_ms(value: object) -> int | None:
    """Coerce ``value`` to a finite millisecond timestamp.

    Mirrors OpenClaw's ``asDateTimestampMs``. Returns ``None``
    for ``None``, non-numeric strings, NaN, and +/- infinity.
    Floats are truncated to integer ms (matching OpenClaw's
    ``Math.trunc``-then-cast behavior).
    """
    result: int | None = None
    if value is None or isinstance(value, bool):
        result = None
    elif isinstance(value, int):
        result = value if -(10**18) <= value <= 10**18 else None
    elif isinstance(value, float):
        result = None if math.isnan(value) or value in (float("inf"), float("-inf")) else int(value)
    elif isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            result = None
        else:
            try:
                parsed: float = float(trimmed)
            except ValueError:
                result = None
            else:
                if math.isnan(parsed) or parsed in (float("inf"), float("-inf")):
                    result = None
                else:
                    result = int(parsed)
    return result


def resolve_expires_at_ms_from_duration_ms(
    duration_ms: object,
    options: dict | None = None,
) -> int | None:
    """Resolve an expiry timestamp from a duration.

    Mirrors OpenClaw's ``resolveExpiresAtMsFromDurationMs``.
    The default ``now_ms`` is the current time. Returns
    ``None`` for non-finite duration or ``now_ms`` values.
    """
    if duration_ms is None or isinstance(duration_ms, bool):
        return None
    duration_value: float
    if isinstance(duration_ms, int | float):
        duration_value = float(duration_ms)
    elif isinstance(duration_ms, str):
        try:
            duration_value = float(duration_ms.strip())
        except ValueError:
            return None
    else:
        return None
    if math.isnan(duration_value) or duration_value in (float("inf"), float("-inf")):
        return None
    if duration_value < 0:
        return None
    now_ms: float | None = None
    if options and "nowMs" in options:
        now_ms = as_date_timestamp_ms(options["nowMs"])
    if now_ms is None:
        now_ms = float(int(time.time() * 1000))
    return int(now_ms + duration_value)


def timestamp_ms_to_iso_string(value: object) -> str | None:
    """Convert a millisecond timestamp to an ISO 8601 string.

    Mirrors OpenClaw's ``timestampMsToIsoString``. Returns
    ``None`` for non-finite / out-of-range timestamps, and an
    ISO 8601 string with millisecond precision (e.g.
    ``"2026-04-05T12:00:00.000Z"``) otherwise. The returned
    string is always in UTC.
    """
    parsed = as_date_timestamp_ms(value)
    if parsed is None:
        return None
    try:
        return (
            datetime.fromtimestamp(parsed / 1000, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return None


__all__ = [
    "as_date_timestamp_ms",
    "parse_strict_positive_integer",
    "resolve_expires_at_ms_from_duration_ms",
    "resolve_timer_timeout_ms",
    "timestamp_ms_to_iso_string",
]
