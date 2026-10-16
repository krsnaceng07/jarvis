"""Web Readability infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``web-readability`` infra
extension (5 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class WebReadabilityPlugin(Plugin):
    """Web Readability infra descriptor."""

    id: str = "web-readability"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Web page content extraction (readability)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


web_readability_plugin = WebReadabilityPlugin()
entry = web_readability_plugin
