"""Linux Node infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``linux-node`` infra
extension (13 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class LinuxNodePlugin(Plugin):
    """Linux Node infra descriptor."""

    id: str = "linux-node"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Linux system node bridge."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


linux_node_plugin = LinuxNodePlugin()
entry = linux_node_plugin
