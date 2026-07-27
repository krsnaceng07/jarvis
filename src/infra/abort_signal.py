"""Abort-signal helpers shared by long-running runtime operations.

OpenClaw parity: ``src/infra/abort-signal.ts``. TS tags plain ``Error``
instances with ``name = "AbortError"``; the Python port uses a dedicated
exception class whose ``name`` attribute carries the same tag so
duck-typed checks (``getattr(err, "name", None) == "AbortError"``) match.
"""
from __future__ import annotations

from typing import Any

__all__ = ["AbortError", "create_abort_error", "is_abort_error"]


class AbortError(Exception):
    """Cancellation error with the DOM-style ``AbortError`` name tag."""

    name = "AbortError"


def create_abort_error(message: str = "Operation aborted.") -> AbortError:
    """Create an abort error matching the host's ``AbortError`` shape."""
    return AbortError(message)


def is_abort_error(error: Any) -> bool:
    """``True`` when ``error`` is an abort-style cancellation error."""
    if isinstance(error, AbortError):
        return True
    return isinstance(error, BaseException) and getattr(error, "name", None) == "AbortError"
