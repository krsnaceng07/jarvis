"""Firecrawl infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``firecrawl`` infra
extension (22 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class FirecrawlPlugin(Plugin):
    """Firecrawl infra descriptor."""

    id: str = "firecrawl"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Firecrawl web scraping provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


firecrawl_plugin = FirecrawlPlugin()
entry = firecrawl_plugin
