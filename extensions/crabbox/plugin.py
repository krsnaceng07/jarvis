"""Crabbox infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``crabbox`` infra
extension (7 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class CrabboxPlugin(Plugin):
    """Crabbox infra descriptor."""

    id: str = "crabbox"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Crabbox multi-tenant chat backend."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


crabbox_plugin = CrabboxPlugin()
entry = crabbox_plugin
