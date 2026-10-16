"""jarvis.logging.state — process-local logging state.

OpenClaw parity: mirrors ``openclaw-main/src/logging/state.ts``.

Public surface:

- :data:`logging_state`
"""
from __future__ import annotations

from typing import Any, Dict


_LOGGING_STATE_KEY = "openclaw.loggingState"


def _create_logging_state() -> Dict[str, Any]:
    return {
        "cachedLogger": None,
        "cachedSettings": None,
        "cachedConsoleSettings": None,
        "overrideSettings": None,
        "invalidEnvLogLevelValue": None,
        "consolePatched": False,
        "forceConsoleToStderr": False,
        "consoleTimestampPrefix": False,
        "consoleSubsystemFilter": None,
        "resolvingConsoleSettings": False,
        "streamErrorHandlersInstalled": False,
        "rawConsole": None,
    }


def _get_or_create_logging_state() -> Dict[str, Any]:
    """Get the process-local logging state, initializing it on first call."""
    if not hasattr(_get_or_create_logging_state, "_state"):
        _get_or_create_logging_state._state = _create_logging_state()
    return _get_or_create_logging_state._state


#: Process-local logging state shared by logger, console capture, and test reset helpers.
logging_state: Dict[str, Any] = _get_or_create_logging_state()


__all__ = ["logging_state"]
