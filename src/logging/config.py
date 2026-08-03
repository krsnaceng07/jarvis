"""jarvis.logging.config — read the logging block from OpenClaw config.

OpenClaw parity: mirrors ``openclaw-main/src/logging/config.ts``.

Public surface:

- :func:`read_logging_config`
- :func:`should_skip_mutating_logging_config_read`
- :func:`reset_logging_config_cache`
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


_cached_logging_config: Optional[Dict[str, Any]] = None


def reset_logging_config_cache() -> None:
    """Clear the cached logging config (for tests)."""
    global _cached_logging_config
    _cached_logging_config = None


def should_skip_mutating_logging_config_read(argv: Optional[List[str]] = None) -> bool:
    """Whether the current CLI invocation is a config schema/validate read.

    Mirrors :func:`shouldSkipMutatingLoggingConfigRead` (``logging/config.ts``).
    """
    argv = argv if argv is not None else sys_argv_safe()
    if len(argv) < 2:
        return False
    primary = argv[0] if argv else ""
    secondary = argv[1] if len(argv) > 1 else ""
    return primary == "config" and secondary in ("schema", "validate")


def sys_argv_safe() -> List[str]:
    argv = getattr(__import__("sys"), "argv", None)
    if isinstance(argv, list):
        return [str(a) for a in argv]
    return []


def _resolve_config_path() -> Optional[str]:
    """Resolve the config path. Mirrors OpenClaw's resolveConfigPath."""
    return os.environ.get("OPENCLAW_CONFIG_PATH") or os.path.join(
        os.path.expanduser("~"), ".jarvis", "config.json"
    )


def read_logging_config() -> Optional[Dict[str, Any]]:
    """Read the logging block from config, caching by resolved config path.

    Mirrors :func:`readLoggingConfig` (``logging/config.ts``).
    """
    global _cached_logging_config
    if should_skip_mutating_logging_config_read():
        return None
    config_path = _resolve_config_path()
    if config_path is None or not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    logging = parsed.get("logging")
    if not isinstance(logging, dict):
        return None
    _cached_logging_config = logging
    return logging


__all__ = [
    "read_logging_config",
    "should_skip_mutating_logging_config_read",
    "reset_logging_config_cache",
]
