"""jarvis_normalization_core.number_coerce — defensive number coercion helpers.

OpenClaw parity: mirrors ``@openclaw/normalization-core/number-coercion``
(``asFiniteNumber``, ``asPositiveFiniteNumber``,
``asNonNegativeFiniteNumber``, ``asFiniteNumberInRange``,
``asSafeIntegerInRange``, ``parseFiniteNumber``, ``parseStrictInteger``,
``parseStrictFiniteNumber``, ``asPositiveSafeInteger``).

Booleans are never numbers here (``isinstance(True, int)`` is ``True``
in Python but ``Number.isFinite(true)`` is ``false`` in JS), so every
helper rejects ``bool`` up front.
"""

from __future__ import annotations

import math
import re

#: Conservative upper bound for timer delays (parity: ``MAX_TIMER_TIMEOUT_MS``).
MAX_TIMER_TIMEOUT_MS = 2_147_000_000
#: Timer bound in whole seconds for env/config inputs.
MAX_TIMER_TIMEOUT_SECONDS = MAX_TIMER_TIMEOUT_MS // 1000
#: Largest timestamp accepted by JavaScript Date.
MAX_DATE_TIMESTAMP_MS = 8_640_000_000_000_000

#: Largest magnitude exactly representable as a float integer.
_MAX_SAFE_INTEGER = 2**53 - 1

#: Strict decimal/scientific token (parity: ``parseStrictFiniteNumber``).
_STRICT_FINITE_RE = re.compile(r"[+-]?(?:(?:\d+\.?\d*)|(?:\.\d+))(?:e[+-]?\d+)?", re.IGNORECASE)

#: Strict base-10 integer token (parity: ``parseStrictInteger``).
_STRICT_INTEGER_RE = re.compile(r"[+-]?\d+")


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def as_finite_number(value: object) -> float | int | None:
    """Return ``value`` only when it is already a finite number."""
    return value if _is_finite_number(value) else None  # type: ignore[return-value]


def as_positive_finite_number(value: object) -> float | int | None:
    """Return a finite number only when it is greater than zero."""
    number = as_finite_number(value)
    return number if number is not None and number > 0 else None


def as_non_negative_finite_number(value: object) -> float | int | None:
    """Return a finite number only when it is zero or greater."""
    number = as_finite_number(value)
    return number if number is not None and number >= 0 else None


def as_finite_number_in_range(
    value: object,
    *,
    min: float | None = None,
    max: float | None = None,
    min_exclusive: bool = False,
    max_exclusive: bool = False,
) -> float | int | None:
    """Return a finite number only when it satisfies the supplied bounds."""
    number = as_finite_number(value)
    if number is None:
        return None
    if min is not None and (number <= min if min_exclusive else number < min):
        return None
    if max is not None and (number >= max if max_exclusive else number > max):
        return None
    return number


def as_safe_integer_in_range(
    value: object,
    *,
    min: int | None = None,
    max: int | None = None,
) -> int | None:
    """Return a safe integer only when it satisfies the supplied bounds."""
    if not isinstance(value, int) or isinstance(value, bool) or abs(value) > _MAX_SAFE_INTEGER:
        return None
    if min is not None and value < min:
        return None
    if max is not None and value > max:
        return None
    return value


def parse_strict_finite_number(value: object) -> float | int | None:
    """Parse finite numbers from numbers or strict numeric string tokens.

    Rejects partial numbers (``"12px"``), ``NaN``/``Infinity`` spellings,
    and overflowing exponents (``"1e999"`` parses to ``inf``).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or not _STRICT_FINITE_RE.fullmatch(token):
        return None
    try:
        parsed = float(token)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def parse_finite_number(value: object) -> float | int | None:
    """Parse finite numbers from number values or strict numeric tokens."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    return parse_strict_finite_number(value)


def parse_strict_integer(value: object) -> int | None:
    """Parse only safe integers or base-10 integer strings."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if abs(value) <= _MAX_SAFE_INTEGER else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and abs(value) <= _MAX_SAFE_INTEGER else None
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or not _STRICT_INTEGER_RE.fullmatch(token):
        return None
    try:
        parsed = int(token)
    except ValueError:
        return None
    return parsed if abs(parsed) <= _MAX_SAFE_INTEGER else None


def as_positive_safe_integer(value: object) -> int | None:
    """Return positive safe integers without string coercion."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or value > _MAX_SAFE_INTEGER
    ):
        return None
    return value


__all__ = [
    "MAX_DATE_TIMESTAMP_MS",
    "MAX_TIMER_TIMEOUT_MS",
    "MAX_TIMER_TIMEOUT_SECONDS",
    "as_finite_number",
    "as_finite_number_in_range",
    "as_non_negative_finite_number",
    "as_positive_finite_number",
    "as_positive_safe_integer",
    "as_safe_integer_in_range",
    "parse_finite_number",
    "parse_strict_finite_number",
    "parse_strict_integer",
]
