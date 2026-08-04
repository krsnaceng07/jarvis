"""jarvis.config.io_health_state — config-IO health state cache.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.health-state.ts``.

Focused minimal port: thin wrapper around a process-local health state
map keyed by config path. Heavy logic (e.g. isAcceptableConfigHealth) is
delegated to caller-provided callables.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


#: Per-config-path health state. Bounded by ``CONFIG_IO_HEALTH_STATE_MAX_SIZE``.
_config_health_state: dict = {}


CONFIG_IO_HEALTH_STATE_MAX_SIZE = 64


def _prune_health_state() -> None:
    while len(_config_health_state) > CONFIG_IO_HEALTH_STATE_MAX_SIZE:
        _config_health_state.pop(next(iter(_config_health_state)), None)


def set_config_io_health_state(config_path: str, value: Any) -> None:
    """Retain a health entry as most-recently used for ``config_path``."""
    if not isinstance(config_path, str):
        return
    _config_health_state.pop(config_path, None)
    _config_health_state[config_path] = value
    _prune_health_state()


def get_config_io_health_state(config_path: str) -> Any:
    """Return the cached health entry for ``config_path``, or None."""
    if not isinstance(config_path, str):
        return None
    return _config_health_state.get(config_path)


def clear_config_io_health_state() -> None:
    """Clear all cached health entries."""
    _config_health_state.clear()


def is_acceptable_config_health(
    config_path: str,
    *,
    is_acceptable_fn: Optional[Callable[[Any], bool]] = None,
) -> bool:
    """Return whether the cached health entry for ``config_path`` is acceptable.

    Mirrors :func:`isAcceptableConfigHealth`
    (``shared/config/io.health-state.ts`).
    """
    if not callable(is_acceptable_fn):
        return False
    state = get_config_io_health_state(config_path)
    if state is None:
        return False
    return bool(is_acceptable_fn(state))


__all__ = [
    "CONFIG_IO_HEALTH_STATE_MAX_SIZE",
    "set_config_io_health_state",
    "get_config_io_health_state",
    "clear_config_io_health_state",
    "is_acceptable_config_health",
]
