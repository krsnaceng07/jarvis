"""jarvis.config.read_best_effort_config_runtime — runtime facade for best-effort config reads.

OpenClaw parity: mirrors
``openclaw-main/src/config/read-best-effort-config.runtime.ts``.

Focused minimal port: this is a thin re-export of the
``read_best_effort_config`` / ``read_best_effort_config_snapshot`` /
``read_source_config_best_effort`` callables from :mod:`jarvis.config.io`.
The actual best-effort read logic is in :mod:`jarvis.config.io` and is wired
up by the runtime when the config IO subsystem is installed.
"""
from __future__ import annotations

from .io import (
    read_best_effort_config,
    read_best_effort_config_snapshot,
)


def read_source_config_best_effort(*args, **kwargs):
    """Facade: delegate to runtime-installed best-effort read.

    Mirrors ``readSourceConfigBestEffort`` from OpenClaw's runtime facade.
    """
    return read_best_effort_config(*args, **kwargs)


__all__ = [
    "read_best_effort_config",
    "read_best_effort_config_snapshot",
    "read_source_config_best_effort",
]
