"""TokenJuice infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``tokenjuice`` infra
extension (10 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class TokenJuicePlugin(Plugin):
    """TokenJuice infra descriptor."""

    id: str = "tokenjuice"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Token usage accounting + reporting."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


tokenjuice_plugin = TokenJuicePlugin()
entry = tokenjuice_plugin
