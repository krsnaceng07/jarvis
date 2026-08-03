"""jarvis.logging.levels — log level constants and helpers.

OpenClaw parity: mirrors ``openclaw-main/src/logging/levels.ts``.

Public surface:

- :data:`ALLOWED_LOG_LEVELS`
- :data:`LogLevel`
- :func:`try_parse_log_level`
- :func:`normalize_log_level`
- :func:`level_to_min_level`
"""
from __future__ import annotations

from typing import List, Optional


#: Accepted logger levels in priority order.
ALLOWED_LOG_LEVELS: List[str] = [
    "silent",
    "fatal",
    "error",
    "warn",
    "info",
    "debug",
    "trace",
]


#: Log level type alias (union of the allowed levels).
LogLevel = str


def try_parse_log_level(level: Optional[str]) -> Optional[LogLevel]:
    """Parse ``level`` into a valid :data:`LogLevel` or return None.

    Mirrors :func:`tryParseLogLevel` (``logging/levels.ts``).
    """
    if not isinstance(level, str):
        return None
    candidate = level.strip().lower()
    if candidate in ALLOWED_LOG_LEVELS:
        return candidate  # type: ignore[return-value]
    return None


def normalize_log_level(level: Optional[str], fallback: LogLevel = "info") -> LogLevel:
    """Normalize ``level`` via :func:`try_parse_log_level` and fall back if invalid.

    Mirrors :func:`normalizeLogLevel` (``logging/levels.ts``).
    """
    parsed = try_parse_log_level(level)
    return parsed if parsed is not None else fallback


#: Mapping from log level → tslog minLevelId (higher = more restrictive).
_LEVEL_TO_MIN_LEVEL: dict = {
    "trace": 1,
    "debug": 2,
    "info": 3,
    "warn": 4,
    "error": 5,
    "fatal": 6,
    "silent": float("inf"),
}


def level_to_min_level(level: LogLevel) -> float:
    """Return the tslog-style min-level id for ``level``.

    Mirrors :func:`levelToMinLevel` (``logging/levels.ts``).
    """
    return _LEVEL_TO_MIN_LEVEL.get(level, float("inf"))


__all__ = [
    "ALLOWED_LOG_LEVELS",
    "LogLevel",
    "try_parse_log_level",
    "normalize_log_level",
    "level_to_min_level",
]
