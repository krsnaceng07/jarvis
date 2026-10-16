"""jarvis.shared.number_coercion — shared numeric coercion facade.

OpenClaw parity: mirrors ``openclaw-main/src/shared/number-coercion.ts``.
"""
from __future__ import annotations


try:
    from jarvis.normalization_core.number_coercion import *  # noqa: F401,F403
except ImportError:  # pragma: no cover — surface remains usable without facade
    pass


def resolve_non_negative_number(value):
    """Return ``value`` if it is a finite, non-negative number, else ``None``.

    Mirrors :func:`resolveNonNegativeNumber` (``shared/number-coercion.ts``).
    """
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    # Reject NaN and infinities.
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if value < 0:
        return None
    return value


__all__ = ["resolve_non_negative_number"]
