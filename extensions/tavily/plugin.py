"""Tavily infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``tavily`` infra
extension (20 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class TavilyPlugin(Plugin):
    """Tavily infra descriptor."""

    id: str = "tavily"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Tavily AI research search provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


tavily_plugin = TavilyPlugin()
entry = tavily_plugin
