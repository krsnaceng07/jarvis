"""jarvis.config.logging — config log-path and log-message helpers.

OpenClaw parity: mirrors
``openclaw-main/src/config/logging.ts``.
"""
from __future__ import annotations

import os
from typing import Optional


def format_config_path(path: str) -> str:
    """Format a config path for operator-facing log output.

    Mirrors :func:`formatConfigPath`
    (``shared/config/logging.ts``).
    """
    if not path:
        return ""
    return path  # display-path normalization is wired by infra/display-path


def format_config_updated_message(
    path: Optional[str] = None,
    *,
    suffix: str = "",
    backup_path=None,
) -> str:
    """Build the config-updated log message, including backup detail only when it exists.

    Mirrors :func:`formatConfigUpdatedMessage`
    (``shared/config/logging.ts``).
    """
    config_path = path or ""
    backup = f"{config_path}.bak" if backup_path is None and config_path else backup_path
    line1 = f"Updated config: {format_config_path(config_path)}"
    if suffix:
        line1 = f"{line1} {suffix}"
    if not backup or not os.path.isfile(backup):
        return line1
    return f"{line1}\n  Backup: {format_config_path(backup)}"


__all__ = [
    "format_config_path",
    "format_config_updated_message",
]
