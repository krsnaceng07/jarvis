"""JARVIS OpenShell infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import OpenShellPlugin, openshell_plugin, entry

__all__ = [
    "OpenShellPlugin",
    "openshell_plugin",
    "entry",
]
