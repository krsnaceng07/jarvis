"""Browser infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``browser`` infra
extension (436 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class BrowserPlugin(Plugin):
    """Browser infra descriptor."""

    id: str = "browser"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Browser automation (Playwright-backed)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


browser_plugin = BrowserPlugin()
entry = browser_plugin
