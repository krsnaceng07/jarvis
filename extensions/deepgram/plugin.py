"""Deepgram infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``deepgram`` infra
extension (11 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DeepgramPlugin(Plugin):
    """Deepgram infra descriptor."""

    id: str = "deepgram"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Deepgram speech-to-text provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


deepgram_plugin = DeepgramPlugin()
entry = deepgram_plugin
