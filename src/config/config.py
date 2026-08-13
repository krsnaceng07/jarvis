"""jarvis.config.config — public config facade re-exports.

OpenClaw parity: mirrors ``openclaw-main/src/config/config.ts``.

The OpenClaw facade re-exports IO/mutation/validation surfaces. The
Python port exposes a thin facade for callers that need a single import
location; the underlying implementations are wired incrementally as the
respective subsystem ports land.
"""
from __future__ import annotations

from typing import Any

from src.config.io import get_runtime_config as _get_runtime_config
from src.config.io import load_config as _load_config
from src.config.io import write_config_file as _write_config_file


def load_config(*args, **kwargs) -> Any:
    """Load the active config.

    Focused minimal port; the full implementation is wired as the IO
    subsystem lands.
    """
    return _load_config(*args, **kwargs)


def get_runtime_config(*args, **kwargs) -> Any:
    """Get the runtime config snapshot."""
    return _get_runtime_config(*args, **kwargs)


def write_config_file(*args, **kwargs) -> Any:
    """Persist a config write."""
    return _write_config_file(*args, **kwargs)


__all__ = ["load_config", "get_runtime_config", "write_config_file"]
