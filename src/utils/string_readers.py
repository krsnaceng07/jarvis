"""String option readers for validating enumerated config values.

OpenClaw parity: ``src/utils/string-readers.ts``.
"""
from __future__ import annotations

from typing import Any, Iterable

__all__ = ["is_string_option"]


def is_string_option(value: Any, options: Iterable[str]) -> bool:
    """``True`` when ``value`` is a string contained in ``options``."""
    return isinstance(value, str) and value in tuple(options)
