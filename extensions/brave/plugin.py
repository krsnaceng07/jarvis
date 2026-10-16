"""Brave infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``brave`` infra
extension (15 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class BravePlugin(Plugin):
    """Brave infra descriptor."""

    id: str = "brave"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Brave web search provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


brave_plugin = BravePlugin()
entry = brave_plugin
