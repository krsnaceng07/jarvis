"""Webhooks infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``webhooks`` infra
extension (11 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class WebhooksPlugin(Plugin):
    """Webhooks infra descriptor."""

    id: str = "webhooks"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "HTTP webhook receiver + dispatcher."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


webhooks_plugin = WebhooksPlugin()
entry = webhooks_plugin
