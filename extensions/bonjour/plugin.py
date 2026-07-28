"""Bonjour Discovery infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``bonjour`` infra
extension (5 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class BonjourDiscoveryPlugin(Plugin):
    """Bonjour Discovery infra descriptor."""

    id: str = "bonjour"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Bonjour/mDNS gateway discovery (macOS auto-advertise)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


bonjour_plugin = BonjourDiscoveryPlugin()
entry = bonjour_plugin
