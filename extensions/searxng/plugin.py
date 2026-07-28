"""SearXNG infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``searxng`` infra
extension (13 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class SearXNGPlugin(Plugin):
    """SearXNG infra descriptor."""

    id: str = "searxng"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "SearXNG self-hosted meta search."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


searxng_plugin = SearXNGPlugin()
entry = searxng_plugin
