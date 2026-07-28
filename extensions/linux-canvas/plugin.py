"""Linux Canvas infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``linux-canvas`` infra
extension (10 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class LinuxCanvasPlugin(Plugin):
    """Linux Canvas infra descriptor."""

    id: str = "linux-canvas"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Linux X11/Wayland canvas surface."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


linux_canvas_plugin = LinuxCanvasPlugin()
entry = linux_canvas_plugin
