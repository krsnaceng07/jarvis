"""Workboard infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``workboard`` infra
extension (42 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class WorkboardPlugin(Plugin):
    """Workboard infra descriptor."""

    id: str = "workboard"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Workboard task management integration (Asana-style)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


workboard_plugin = WorkboardPlugin()
entry = workboard_plugin
