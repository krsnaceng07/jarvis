"""JARVIS DeepInfra provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import DeepInfraProvider, deepinfra_provider, entry

__all__ = [
    "DeepInfraProvider",
    "deepinfra_provider",
    "entry",
]
