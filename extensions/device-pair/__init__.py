"""JARVIS Device Pairing infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import DevicePairingPlugin, device_pair_plugin, entry

__all__ = [
    "DevicePairingPlugin",
    "device_pair_plugin",
    "entry",
]
