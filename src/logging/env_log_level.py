"""jarvis.logging.env_log_level — resolve the OPENCLAW_LOG_LEVEL env override.

OpenClaw parity: mirrors ``openclaw-main/src/logging/env-log-level.ts``.

Public surface:

- :func:`resolve_env_log_level_override`
- :func:`reset_invalid_env_log_level_state`
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from .levels import ALLOWED_LOG_LEVELS, try_parse_log_level


_INVALID_KEY = "invalidEnvLogLevelValue"


def _logging_state() -> dict:
    """Lazy import to avoid circular import with state.py."""
    from .state import logging_state
    return logging_state


def resolve_env_log_level_override() -> Optional[str]:
    """Resolve ``OPENCLAW_LOG_LEVEL`` once per value, warning on invalid change.

    Mirrors :func:`resolveEnvLogLevelOverride` (``logging/env-log-level.ts``).
    """
    raw = (os.environ.get("OPENCLAW_LOG_LEVEL") or "").strip()
    state = _logging_state()
    if not raw:
        state[_INVALID_KEY] = None
        return None
    parsed = try_parse_log_level(raw)
    if parsed is not None:
        state[_INVALID_KEY] = None
        return parsed
    if state.get(_INVALID_KEY) != raw:
        state[_INVALID_KEY] = raw
        sys.stderr.write(
            f"[jarvis] Ignoring invalid OPENCLAW_LOG_LEVEL=\"{raw}\" "
            f"(allowed: {''.join(ALLOWED_LOG_LEVELS)}).\n"
        )
    return None


def reset_invalid_env_log_level_state() -> None:
    """Clear the process-local invalid-log-level tracker (for tests)."""
    _logging_state()[_INVALID_KEY] = None


__all__ = [
    "resolve_env_log_level_override",
    "reset_invalid_env_log_level_state",
]
