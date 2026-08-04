"""jarvis.config.config — public config facade re-exports.

OpenClaw parity: mirrors ``openclaw-main/src/config/config.ts``.

The OpenClaw facade re-exports IO/mutation/validation surfaces. The
Python port exposes a thin facade for callers that need a single import
location; the underlying implementations are wired incrementally as the
respective subsystem ports land.
"""
from __future__ import annotations

from typing import Any


def load_config(*args, **kwargs) -> Any:
    """Load the active config.

    Focused minimal port; the full implementation is wired as the IO
    subsystem lands.
    """
    raise NotImplementedError("load_config: wire as the config-IO port lands")


def get_runtime_config(*args, **kwargs) -> Any:
    """Get the runtime config snapshot."""
    raise NotImplementedError("get_runtime_config: wire as the runtime-snapshot port lands")


def write_config_file(*args, **kwargs) -> Any:
    """Persist a config write."""
    raise NotImplementedError("write_config_file: wire as the config-IO port lands")


__all__ = ["load_config", "get_runtime_config", "write_config_file"]
