"""jarvis.config.io_state — config-IO warning/fingerprint state.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.state.ts``.

Focused minimal port: the dedupe cache is delegated to caller-provided
``create_dedupe_cache`` until the infra/dedupe module lands.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


CONFIG_IO_WARNING_CACHE_MAX_SIZE = 4096


def _create_dedupe_cache_stub() -> dict:
    """Minimal dedupe-cache placeholder (always-miss)."""
    class _Stub:
        def check(self, _key: str) -> bool:
            return False

        def add(self, _key: str) -> None:
            pass

    return _Stub()


#: Warnings that have been logged for a given config path. Bounded to ``CONFIG_IO_WARNING_CACHE_MAX_SIZE``.
logged_invalid_configs: Any = _create_dedupe_cache_stub()
#: Per-config warning fingerprints.
logged_config_warning_fingerprints: dict = {}
#: Versions that have already triggered the future-touched-version warning.
warned_future_touched_versions: Any = _create_dedupe_cache_stub()
#: Owner-display secrets retained by config path.
auto_owner_display_secret_by_path: dict = {}


def set_bounded_config_io_warning_entry(
    map_: dict,
    key: Any,
    value: Any,
    *,
    prune_map_to_max_size_fn: Optional[Callable] = None,
) -> None:
    """Retain a warning entry as most-recently used while enforcing the shared bound.

    Mirrors :func:`setBoundedConfigIoWarningEntry`
    (``shared/config/io.state.ts`).
    """
    if key in map_:
        del map_[key]
    map_[key] = value
    if callable(prune_map_to_max_size_fn):
        prune_map_to_max_size_fn(map_, CONFIG_IO_WARNING_CACHE_MAX_SIZE)


__all__ = [
    "CONFIG_IO_WARNING_CACHE_MAX_SIZE",
    "logged_invalid_configs",
    "logged_config_warning_fingerprints",
    "warned_future_touched_versions",
    "auto_owner_display_secret_by_path",
    "set_bounded_config_io_warning_entry",
]
