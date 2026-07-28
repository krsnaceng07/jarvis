"""Diffs infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``diffs`` infra
extension (38 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DiffsPlugin(Plugin):
    """Diffs infra descriptor."""

    id: str = "diffs"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Code diff renderer."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


diffs_plugin = DiffsPlugin()
entry = diffs_plugin
