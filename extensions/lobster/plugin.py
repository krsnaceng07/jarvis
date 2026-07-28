"""Lobster infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``lobster`` infra
extension (15 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class LobsterPlugin(Plugin):
    """Lobster infra descriptor."""

    id: str = "lobster"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Lobster workflow runtime."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


lobster_plugin = LobsterPlugin()
entry = lobster_plugin
