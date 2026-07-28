"""JARVIS Bonjour Discovery infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import BonjourDiscoveryPlugin, bonjour_plugin, entry

__all__ = [
    "BonjourDiscoveryPlugin",
    "bonjour_plugin",
    "entry",
]
