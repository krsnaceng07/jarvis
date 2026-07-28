"""ACPX infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``acpx`` infra
extension (47 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class ACPXPlugin(Plugin):
    """ACPX infra descriptor."""

    id: str = "acpx"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Agent Client Protocol executor."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


acpx_plugin = ACPXPlugin()
entry = acpx_plugin
