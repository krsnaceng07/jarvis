"""jarvis_sdk.number_runtime — strict number parsing.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/number-runtime``'s
``parseStrictPositiveInteger`` and ``resolveTimerTimeoutMs``.

Used by ``memory-lancedb`` to parse CLI args and to set the
embeddings request timeout (capped to a positive integer in
milliseconds).

Architecture
============
OpenClaw has a single module that wraps the strict-positive-int
parser and the timer-timeout resolver. The Python equivalent
is the same: ``parse_strict_positive_integer`` raises on garbage
input; ``resolve_timer_timeout_ms`` clamps a value to a positive
integer with a fallback.

Parity
======
- ``parse_strict_positive_integer(value)`` → ``int`` or
  ``None`` (if value is empty/undefined). Raises ``ValueError``
  on negative or non-integer strings.
- ``resolve_timer_timeout_ms(raw, fallback)`` → ``int``
  (clamped to >= 1). Treats ``None``, ``0``, and negative values
  as "use fallback".
"""

from __future__ import annotations


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


__all__ = ["parse_strict_positive_integer", "resolve_timer_timeout_ms"]
