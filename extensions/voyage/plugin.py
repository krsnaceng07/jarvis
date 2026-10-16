"""Voyage infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``voyage`` infra
extension (8 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class VoyagePlugin(Plugin):
    """Voyage infra descriptor."""

    id: str = "voyage"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Voyage AI embeddings provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


voyage_plugin = VoyagePlugin()
entry = voyage_plugin
