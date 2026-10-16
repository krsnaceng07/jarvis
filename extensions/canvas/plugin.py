"""Canvas infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``canvas`` infra
extension (46 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class CanvasPlugin(Plugin):
    """Canvas infra descriptor."""

    id: str = "canvas"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Live canvas surface (display + interactive)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


canvas_plugin = CanvasPlugin()
entry = canvas_plugin
