"""Exa infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``exa`` infra
extension (13 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class ExaPlugin(Plugin):
    """Exa infra descriptor."""

    id: str = "exa"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Exa web search provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


exa_plugin = ExaPlugin()
entry = exa_plugin
