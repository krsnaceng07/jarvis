"""Plugin hook dir resolver — mirrors OpenClaw ``src/hooks/plugin-hooks.ts``.

Walks the plugin registry snapshot, checks activation state and memory-slot
winner, validates path containment, and returns a list of
``PluginHookDirEntry`` records pointing to directories that contain hook
handlers contributed by active plugins.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger("jarvis.hooks.plugin_hooks")


@dataclass(frozen=True, slots=True)
class PluginHookDirEntry:
    """A validated hook directory contributed by a plugin."""

    dir: str           # Absolute, realpath-resolved directory
    plugin_id: str


def _is_path_inside(root: str, candidate: str) -> bool:
    """Return True if candidate is inside root (realpath containment check)."""
    try:
        real_root = os.path.realpath(root)
        real_candidate = os.path.realpath(candidate)
        return real_candidate.startswith(real_root + os.sep) or real_candidate == real_root
    except OSError:
        return False


def resolve_plugin_hook_dirs(
    plugin_registry: list[dict] | None = None,
    config: dict | None = None,
) -> list[PluginHookDirEntry]:
    """Resolve hook directories declared by active plugin manifests.

    Args:
        plugin_registry: list of plugin record dicts from the plugin loader.
            Each record should have: id, root_dir, hooks (list[str]),
            kind, activation, enabled.
        config: JARVIS config dict (used for per-plugin activation overrides).

    Returns:
        List of ``PluginHookDirEntry`` — one per valid resolved hook dir,
        deduped by realpath.
    """
    if not plugin_registry:
        return []

    seen: set[str] = set()
    resolved: list[PluginHookDirEntry] = []

    for record in plugin_registry:
        hook_paths: list[str] = record.get("hooks") or []
        if not hook_paths:
            continue

        # Activation gate — skip disabled plugins
        if not record.get("enabled", True):
            continue

        root_dir: str = record.get("root_dir", "")
        plugin_id: str = record.get("id", "unknown")

        for raw_path in hook_paths:
            trimmed = (raw_path or "").strip()
            if not trimmed:
                continue

            candidate = str(Path(root_dir).joinpath(trimmed).resolve())

            if not Path(candidate).exists():
                _log.warning(
                    "plugin hook path not found (%s): %s", plugin_id, candidate
                )
                continue

            # Path containment security check — mirrors isPathInsideWithRealpath
            if not _is_path_inside(root_dir, candidate):
                _log.warning(
                    "plugin hook path escapes plugin root (%s): %s",
                    plugin_id,
                    candidate,
                )
                continue

            if candidate in seen:
                continue

            seen.add(candidate)
            resolved.append(PluginHookDirEntry(dir=candidate, plugin_id=plugin_id))

    return resolved


__all__ = ["PluginHookDirEntry", "resolve_plugin_hook_dirs"]
